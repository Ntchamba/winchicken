"""Integration chain 3 — batch creation -> daily logs (weight, mortality) -> batch evolution
(weekly KPI, growth curve) -> farm health score -> "Bilan global" overview tree. Through the API,
the way the app writes and reads them, against the real database.
"""
import datetime as dt
from unittest import mock

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.alerts.models import Alert, AlertRuleType
from apps.batches.models import PoultryBatch
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse

TODAY = dt.date(2026, 9, 24)


@mock.patch('django.utils.timezone.localdate', return_value=TODAY)
class BatchToOverviewChainTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Santé')
        self.admin = User.objects.create_user(email='admin@sante.local', password='x', name='A', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(self.admin)
        self.worker = User.objects.create_user(email='w@sante.local', password='x', name='W', role=UserRole.WORKER, farm=self.farm)
        create_role_profile(self.worker)
        self.houses = [
            PoultryHouse.objects.create(house_code=f'H-{self.farm.id}-00{i}', farm=self.farm, name=f'B{i}', max_capacity=1000)
            for i in (1, 2)
        ]

    def create_batch(self, house, start, count=1000, name='Bande'):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post('/api/batches/', {
            'house_code': house.house_code, 'name': name, 'production_type': 'BROILER',
            'initial_count': count, 'start_date': start.isoformat(),
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data['batch_code']

    def log(self, code, day, **fields):
        self.client.force_authenticate(user=self.worker)
        body = {'date': day.isoformat(), 'mortality': None, 'eggsCollected': None, 'avgSampleWeight': None, **fields}
        return self.client.put(f'/api/batches/{code}/daily-logs/quick-entry/', body, format='json')

    def get(self, url, **params):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(url, params)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_logs_flow_into_kpis_curve_health_and_overview(self, _today):
        start = TODAY - dt.timedelta(days=13)  # day 13: weeks 1 and 2
        code = self.create_batch(self.houses[0], start)
        for offset, deaths, weight in [(0, 5, 0.042), (6, 3, 0.18), (7, 2, None), (13, 4, 0.45)]:
            response = self.log(code, start + dt.timedelta(days=offset), mortality=deaths, avgSampleWeight=weight)
            self.assertEqual(response.status_code, 200, response.data)

        kpi = self.get(f'/api/batches/{code}/kpi/weekly/')
        self.assertEqual([(w['week'], w['mortalityPct'], w['avgWeightKg']) for w in kpi['weeks']], [(1, 0.8, 0.18), (2, 0.6, 0.45)])
        # No feed was ever recorded: the FCR is unknown, not a perfect 0.
        self.assertEqual([w['feedConversionRatio'] for w in kpi['weeks']], [None, None])

        [curve] = [c for c in self.get('/api/batches/growth-curves/') if c['batchCode'] == code]
        self.assertEqual([(p['dayOfCycle'], p['survivalPct']) for p in curve['points']], [(0, 99.5), (6, 99.2), (7, 99.0), (13, 98.6)])

        self.assertEqual(self.get('/api/batches/health-score/')['tier'], 'good')
        overview = self.get('/api/farm/overview/')
        self.assertEqual(overview['branches']['health']['tier'], 'good')
        self.assertEqual(overview['branches']['health']['value'], 986)
        self.assertEqual(self.get(f'/api/batches/{code}/')['current_count'], 986)

    def test_a_mortality_spike_turns_health_to_watch_and_the_overview_names_it(self, _today):
        start = TODAY - dt.timedelta(days=13)
        code = self.create_batch(self.houses[0], start, name='Bande Nord')
        self.log(code, start, mortality=5)
        self.log(code, TODAY, mortality=40)  # week 2: 4 % > 5 % / 2 weeks
        score = self.get('/api/batches/health-score/')
        self.assertEqual(score['tier'], 'watch')
        self.assertIn('mortalité au-dessus de la norme sur la bande Bande Nord', score['reason'])
        overview = self.get('/api/farm/overview/')
        self.assertEqual(overview['branches']['health']['tier'], 'watch')
        self.assertIn('health', overview['core']['drivers'])

    def test_two_batches_in_breach_make_it_critical(self, _today):
        start = TODAY - dt.timedelta(days=13)
        for house in self.houses:
            code = self.create_batch(house, start, name=house.name)
            self.log(code, start, mortality=1)  # week 1 logged too: the rule divides by logged weeks
            self.log(code, TODAY, mortality=40)
        self.assertEqual(self.get('/api/batches/health-score/')['tier'], 'critical')
        self.assertEqual(self.get('/api/farm/overview/')['core']['tier'], 'critical')

    def test_a_new_batch_with_no_logs_reads_cleanly_everywhere(self, _today):
        code = self.create_batch(self.houses[0], TODAY)
        self.assertEqual(self.get(f'/api/batches/{code}/kpi/weekly/')['weeks'], [])
        self.assertEqual(self.get('/api/batches/health-score/')['tier'], 'good')
        self.assertEqual(self.get('/api/farm/overview/')['branches']['health']['value'], 1000)

    def test_bad_logs_are_refused_and_change_nothing(self, _today):
        start = TODAY - dt.timedelta(days=5)
        code = self.create_batch(self.houses[0], start, count=100)
        self.assertEqual(self.log(code, TODAY, mortality=101).status_code, 400)            # more than the flock
        self.assertEqual(self.log(code, TODAY + dt.timedelta(days=1), mortality=1).status_code, 400)  # future
        self.assertEqual(self.log(code, start - dt.timedelta(days=1), mortality=1).status_code, 400)  # before start
        self.assertEqual(self.log(code, TODAY, avgSampleWeight=-1).status_code, 400)
        self.assertEqual(PoultryBatch.objects.get(batch_code=code).daily_logs.count(), 0)
        self.assertEqual(self.get('/api/farm/overview/')['branches']['health']['value'], 100)

    def test_a_second_active_batch_in_the_same_house_is_refused(self, _today):
        self.create_batch(self.houses[0], TODAY)
        self.client.force_authenticate(user=self.admin)
        response = self.client.post('/api/batches/', {
            'house_code': self.houses[0].house_code, 'production_type': 'BROILER', 'initial_count': 10, 'start_date': TODAY.isoformat(),
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_feed_logged_without_water_raises_no_consumption_alarm(self, _today):
        # Water left blank is stored as 0; a ratio of 0 is "not recorded", not "hors norme".
        code = self.create_batch(self.houses[0], TODAY - dt.timedelta(days=3))
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(f'/api/batches/{code}/daily-logs/', {'log_date': TODAY.isoformat(), 'feed_consumed_kg': 55}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(Alert.objects.filter(rule__rule_type=AlertRuleType.CONSUMPTION_DEVIATION).exists())

    def test_feed_and_water_out_of_ratio_raise_the_consumption_alarm_and_health_watch(self, _today):
        code = self.create_batch(self.houses[0], TODAY - dt.timedelta(days=3))
        self.client.force_authenticate(user=self.admin)
        self.client.post(f'/api/batches/{code}/daily-logs/', {'log_date': TODAY.isoformat(), 'feed_consumed_kg': 50, 'water_consumed_l': 50}, format='json')
        [alert] = Alert.objects.filter(rule__rule_type=AlertRuleType.CONSUMPTION_DEVIATION)
        self.assertEqual(alert.message, f'Ratio eau/aliment 1 hors norme 1,6-2,2 — {code}')
        self.assertEqual(self.get('/api/batches/health-score/')['tier'], 'watch')
