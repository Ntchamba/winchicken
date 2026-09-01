from datetime import date

from rest_framework import status
from rest_framework.test import APITestCase

from apps.batches.models import PoultryBatch, ProductionType
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse
from apps.protocols.models import ProtocolCategory, ProtocolTemplate, ProtocolTimeSlot


class ScheduleViewMultiDayTests(APITestCase):
    """GET /api/protocols/schedule/ (Bug 3 fix, 2026-08-27, docs/deviations.md) — a
    ProtocolTemplate line spanning several days must appear on every one of those days in the
    calendar month view, not just the first (the previous implementation read PROTOCOL_TASK
    AlertRule rows, generated for a line's first due day only)."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Calendrier Test')
        self.user = User.objects.create_user(
            email='admin@calendar-test.local', password='x', name='Admin', role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.user)
        self.client.force_authenticate(user=self.user)

        self.house = PoultryHouse.objects.create(house_code='H-CAL-1', farm=self.farm, name='Salle 1', max_capacity=1000)
        self.category = ProtocolCategory.objects.create(house=self.house, label='Alimentation', icon='Soup')
        # Day 1 to day 15 of the cycle — day_of_cycle = (day - start_date).days, so day_of_cycle
        # 1 falls on start_date + 1 (2026-03-02), matching this project's existing convention
        # (see apps.houses.tests.TaskAssignmentTests.setUp's own "day_of_cycle=1" comment).
        # Batch starts 2026-03-01: day 1 = 2026-03-02, day 15 = 2026-03-16.
        ProtocolTemplate.objects.create(
            house=self.house, category=self.category,
            from_value=1, from_unit='DAY', to_value=15, to_unit='DAY', until_end=False,
            what='Aliment démarrage',
        )
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-CAL-1', house=self.house, production_type=ProductionType.BROILER,
            initial_count=500, start_date=date(2026, 3, 1),
        )

    def test_multi_day_line_appears_on_every_day_of_its_range(self):
        response = self.client.get('/api/protocols/schedule/', {'month': '2026-03'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        dates = sorted(entry['date'] for entry in response.data)
        expected = [f'2026-03-{day:02d}' for day in range(2, 17)]
        self.assertEqual(dates, expected)

    def test_no_entries_outside_the_line_s_range(self):
        response = self.client.get('/api/protocols/schedule/', {'month': '2026-03'})
        for entry in response.data:
            self.assertLessEqual(entry['date'], '2026-03-16')

    def test_no_entries_in_a_month_before_the_batch_started(self):
        response = self.client.get('/api/protocols/schedule/', {'month': '2026-02'})
        self.assertEqual(response.data, [])

    def test_until_end_line_keeps_appearing_every_day_after_its_start(self):
        ProtocolTemplate.objects.create(
            house=self.house, category=self.category,
            from_value=20, from_unit='DAY', until_end=True, what='Nettoyage quotidien',
        )
        response = self.client.get('/api/protocols/schedule/', {'month': '2026-03'})
        cleaning_dates = sorted(e['date'] for e in response.data if e['what'] == 'Nettoyage quotidien')
        # day_of_cycle 20 = start_date (2026-03-01) + 20 = 2026-03-21, no upper bound — every
        # remaining day of the visible month.
        expected = [f'2026-03-{day:02d}' for day in range(21, 32)]
        self.assertEqual(cleaning_dates, expected)


class OnboardingTimeSlotTests(APITestCase):
    """POST /api/protocols/onboarding/ also writes `ProtocolTimeSlot` rows (Bug 1 fix,
    2026-08-27, docs/deviations.md) — the "Horaires" section must work from the onboarding
    wizard's protocol step, not just the "Modifier" edit modal/page (same shared
    HouseProtocolForm component, same OnboardingView/HouseProtocolView write path)."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Onboarding Horaires Test')
        self.admin = User.objects.create_user(
            email='admin@onboarding-slot-test.local', password='x', name='Admin', role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.admin)
        self.client.force_authenticate(user=self.admin)

    def test_onboarding_creates_time_slots_for_a_protocol_line(self):
        payload = {
            'house': {'name': 'Bâtiment A', 'maxCapacity': 500},
            'protocolLines': [{
                'categoryIndex': 0, 'from_value': 1, 'from_unit': 'DAY',
                'to_value': None, 'to_unit': 'DAY', 'until_end': True, 'what': 'Nourrissage', 'details': '',
                'time_slots': [{'start_time': '07:00', 'end_time': '09:00'}, {'start_time': '18:00', 'end_time': '20:00'}],
            }],
        }
        response = self.client.post('/api/protocols/onboarding/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        line = ProtocolTemplate.objects.get(house__house_code=response.data['house']['houseCode'])
        self.assertEqual(ProtocolTimeSlot.objects.filter(protocol_line=line).count(), 2)
        self.assertEqual(len(response.data['protocolLines'][0]['time_slots']), 2)


class OnboardingBatchNameRequiredTests(APITestCase):
    """Part A: a batch may not be created with a blank / whitespace-only name."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Batch Name Test')
        self.admin = User.objects.create_user(
            email='admin@batch-name-test.local', password='x', name='Admin', role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.admin)
        self.client.force_authenticate(user=self.admin)

    def _payload(self, batch_name):
        return {
            'house': {'name': 'Bâtiment A', 'maxCapacity': 500},
            'batch': {'name': batch_name, 'initialCount': 500, 'productionType': 'BROILER'},
            'protocolLines': [{
                'categoryIndex': 0, 'from_value': 1, 'from_unit': 'DAY', 'to_value': 15, 'to_unit': 'DAY',
                'until_end': False, 'what': 'Nourrissage', 'details': '',
            }],
        }

    def test_blank_batch_name_is_rejected_with_a_field_error(self):
        for bad in ('', '   ', '\t\n'):
            response = self.client.post('/api/protocols/onboarding/', self._payload(bad), format='json')
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
            self.assertIn('name', response.data.get('batch', {}))
            self.assertFalse(PoultryBatch.objects.exists())
            self.assertFalse(PoultryHouse.objects.exists())  # nothing half-created

    def test_valid_batch_name_is_accepted_and_stored_trimmed(self):
        response = self.client.post('/api/protocols/onboarding/', self._payload('  Bande printemps  '), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(PoultryBatch.objects.get().name, 'Bande printemps')


class ScheduleViewTimeSlotTests(APITestCase):
    """GET /api/protocols/schedule/ showing `ProtocolTimeSlot` windows (calendar time-slot
    display fix, 2026-08-27, docs/deviations.md) — a line with time slots must generate one
    calendar entry per slot, each carrying its own window; a line with none is unaffected."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Calendrier Horaires Test')
        self.user = User.objects.create_user(
            email='admin@calendar-slot-test.local', password='x', name='Admin', role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.user)
        self.client.force_authenticate(user=self.user)
        self.house = PoultryHouse.objects.create(house_code='H-CALSLOT-1', farm=self.farm, name='Salle 1', max_capacity=1000)
        self.category = ProtocolCategory.objects.create(house=self.house, label='Alimentation', icon='Soup')
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-CALSLOT-1', house=self.house, production_type=ProductionType.BROILER,
            initial_count=500, start_date=date(2026, 3, 1),
        )

    def test_line_with_two_slots_produces_two_entries_with_their_own_times(self):
        line = ProtocolTemplate.objects.create(
            house=self.house, category=self.category, from_value=1, until_end=True, what='Nourrissage',
        )
        ProtocolTimeSlot.objects.create(protocol_line=line, start_time='07:00', end_time='09:00')
        ProtocolTimeSlot.objects.create(protocol_line=line, start_time='18:00', end_time='20:00')

        response = self.client.get('/api/protocols/schedule/', {'month': '2026-03'})
        entries = [e for e in response.data if e['date'] == '2026-03-02']  # day_of_cycle=1
        self.assertEqual(len(entries), 2)
        windows = sorted((e['startTime'], e['endTime']) for e in entries)
        self.assertEqual(windows, [('07h00', '09h00'), ('18h00', '20h00')])
        self.assertEqual(len({e['id'] for e in entries}), 2)  # distinct ids, not deduped/collided

    def test_line_with_no_slots_produces_one_entry_with_null_times(self):
        ProtocolTemplate.objects.create(
            house=self.house, category=self.category, from_value=1, to_value=5, what='Nettoyage',
        )
        response = self.client.get('/api/protocols/schedule/', {'month': '2026-03'})
        entries = [e for e in response.data if e['date'] == '2026-03-02']
        self.assertEqual(len(entries), 1)
        self.assertIsNone(entries[0]['startTime'])
        self.assertIsNone(entries[0]['endTime'])
