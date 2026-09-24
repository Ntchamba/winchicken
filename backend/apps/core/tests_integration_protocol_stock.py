"""Integration chain 1 — protocol line -> task -> completion -> stock deduction -> movement ->
low-stock alert -> SMS dispatch. Every step through the public API, against the real database.

The unit tests (apps.protocols.tests_completion) pin each link on its own; these walk the chain
the way the farm does: an admin saves a protocol, the worker sees the task, taps "Marquer comme
fait", and the manager's phone gets the low-stock SMS.
"""
import datetime as dt
import threading
from decimal import Decimal
from unittest import mock

from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient, APITestCase

from apps.alerts.tasks import send_sms_task
from apps.alerts.models import Alert, AlertRuleType, NotificationChannel, NotificationPreference, SmsMessage, SmsStatus
from apps.batches.models import BatchStatus, PoultryBatch, ProductionType
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse
from apps.protocols.models import ProtocolCategory, ProtocolTemplate, TaskCompletion
from apps.stock.models import MovementType, StockCategory, StockItem, StockMovement


def build_farm(tag):
    """A farm with an admin (phone + LOW_STOCK SMS opt-in), a worker, one house with an active
    batch on day 1 of its cycle, and 150 kg of feed against a 100 kg alert threshold."""
    farm = Farm.objects.create(name=f'Ferme {tag}')
    admin = User.objects.create_user(
        email=f'admin@{tag}.local', password='x', name='Paul Admin', role=UserRole.ADMIN, farm=farm, phone='+237600000001',
    )
    create_role_profile(admin)
    NotificationPreference.objects.create(
        user=admin, rule_type=AlertRuleType.LOW_STOCK, preferred_channel=NotificationChannel.SMS, active=True,
    )
    worker = User.objects.create_user(
        email=f'worker@{tag}.local', password='x', name='Awa Ouvrière', role=UserRole.WORKER, farm=farm,
    )
    create_role_profile(worker)
    house = PoultryHouse.objects.create(house_code=f'H-{farm.id}-001', farm=farm, name='Poulailler A', max_capacity=500)
    today = timezone.localdate()
    batch = PoultryBatch.objects.create(
        batch_code=f'B-{farm.id}-1', house=house, name='Bande A', production_type=ProductionType.BROILER,
        initial_count=500, start_date=today - dt.timedelta(days=1),
        planned_end_date=today + dt.timedelta(days=55), status=BatchStatus.ACTIVE,
    )
    feed = StockCategory.objects.get(farm=farm, kind='FEED')
    item = StockItem.objects.create(
        item_code=f'FEE-{farm.id}-001', farm=farm, category=feed, name='Provende', unit='kg',
        alert_threshold=100, unit_price=Decimal('450.00'),
    )
    StockMovement.objects.create(item=item, movement_type=MovementType.IN, quantity=150, movement_date=today)
    return farm, admin, worker, house, batch, item


# Console provider: the stack runs SMS_PROVIDER=twilio, and a test must never reach a real gateway.
@override_settings(SMS_PROVIDER='console')
class ProtocolToStockToAlertChainTests(APITestCase):
    def setUp(self):
        self.farm, self.admin, self.worker, self.house, self.batch, self.item = build_farm('chaine1')
        self.feeding = ProtocolCategory.objects.get(house=self.house, label='Alimentation')

    # --- helpers: the calls the app makes --------------------------------------------------

    def save_protocol(self, *lines):
        self.client.force_authenticate(user=self.admin)
        response = self.client.put(f'/api/houses/{self.house.house_code}/protocol/', {'lines': list(lines)}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def feed_line(self, **overrides):
        return {
            'category': self.feeding.id, 'from_value': 1, 'from_unit': 'DAY', 'until_end': True,
            'what': 'Aliment démarrage', 'details': '', 'time_slots': [],
            'stock_item': self.item.item_code, 'quantity_per_day': 40, **overrides,
        }

    def tasks(self, user=None):
        self.client.force_authenticate(user=user or self.worker)
        response = self.client.get(f'/api/houses/{self.house.house_code}/tasks-now/')
        self.assertEqual(response.status_code, 200)
        return response.data['tasks']

    def complete(self, line_id, user=None, **body):
        self.client.force_authenticate(user=user or self.worker)
        return self.client.post(f'/api/houses/{self.house.house_code}/tasks-now/{line_id}/complete/', body, format='json')

    def on_hand(self):
        self.client.force_authenticate(user=self.admin)
        items = self.client.get(f'/api/farms/{self.farm.id}/stock-items/').data['items']
        return next(i for i in items if i['item_code'] == self.item.item_code)['current_quantity']

    def low_stock_alerts(self):
        self.client.force_authenticate(user=self.admin)
        rows = self.client.get('/api/alerts/', {'open': '1'}).data['results']
        return [a for a in rows if a['ruleType'] == AlertRuleType.LOW_STOCK]

    # --- the chain --------------------------------------------------------------------------

    def test_the_whole_chain_from_protocol_to_sms(self):
        line, second = self.save_protocol(self.feed_line(), self.feed_line(what='Complément'))

        [task] = [t for t in self.tasks() if t['id'] == str(line['id'])]
        self.assertFalse(task['done'])

        response = self.complete(line['id'])
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['movement']['quantity'], 40)
        self.assertEqual(self.on_hand(), 110)
        self.assertEqual(self.low_stock_alerts(), [])  # 110 >= 100: nothing fires yet

        [task] = [t for t in self.tasks() if t['id'] == str(line['id'])]
        self.assertTrue(task['done'])

        movement = StockMovement.objects.get(item=self.item, movement_type=MovementType.OUT)
        self.assertEqual((movement.quantity, movement.batch_id, movement.protocol_line_id), (40, self.batch.batch_code, line['id']))
        self.client.force_authenticate(user=self.admin)
        listed = self.client.get('/api/stock-movements/').data
        listed = listed['results'] if isinstance(listed, dict) else listed
        self.assertIn(movement.id, [m['id'] for m in listed])

        # The second line takes the level under the threshold: the alert fires and the opted-in
        # admin's SMS is queued after commit, then sent by the (console) provider.
        # `.delay` would hand the SMS to the live Redis worker, which reads another database;
        # the task body runs here instead, against this test's rows.
        with mock.patch('apps.alerts.services.send_sms_task.delay', side_effect=send_sms_task), \
                self.captureOnCommitCallbacks(execute=True):
            response = self.complete(second['id'])
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.on_hand(), 70)

        [alert] = self.low_stock_alerts()
        self.assertEqual(alert['message'], 'Provende sous le seuil (70 kg < 100 kg)')
        [sms] = SmsMessage.objects.filter(alert_id=alert['id'])
        self.assertEqual(sms.recipient, '+237600000001')
        self.assertEqual(sms.provider_status, SmsStatus.SENT)

    def test_insufficient_stock_asks_first_and_writes_nothing_then_force_goes_negative(self):
        [line] = self.save_protocol(self.feed_line(quantity_per_day=200))

        response = self.complete(line['id'])
        self.assertEqual(response.data['status'], 'insufficient_stock')
        self.assertEqual(response.data['shortfall'], {
            'itemCode': self.item.item_code, 'itemName': 'Provende', 'unit': 'kg', 'needed': 200, 'onHand': 150,
        })
        self.assertEqual(self.on_hand(), 150)
        self.assertFalse(TaskCompletion.objects.exists())
        self.assertFalse(Alert.objects.exists())

        response = self.complete(line['id'], force=True)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.on_hand(), -50)
        self.assertEqual(len(self.low_stock_alerts()), 1)

    def test_a_line_with_a_resource_but_no_quantity_completes_without_touching_stock(self):
        [line] = self.save_protocol(self.feed_line(quantity_per_day=None))
        response = self.complete(line['id'])
        self.assertEqual(response.status_code, 201)
        self.assertIsNone(response.data['movement'])
        self.assertEqual(self.on_hand(), 150)

    def test_a_dose_per_bird_line_deducts_for_the_birds_alive_that_day(self):
        [line] = self.save_protocol(self.feed_line(quantity_per_day=None, dose_per_bird=0.1))
        self.client.force_authenticate(user=self.worker)
        self.client.put(
            f'/api/batches/{self.batch.batch_code}/daily-logs/quick-entry/',
            {'date': timezone.localdate().isoformat(), 'mortality': 20}, format='json',
        )
        response = self.complete(line['id'])
        self.assertEqual(response.data['movement']['quantity'], 48.0)  # 0.1 kg x 480 birds
        self.assertEqual(self.on_hand(), 102)

    def test_no_active_batch_is_refused_in_french(self):
        [line] = self.save_protocol(self.feed_line())
        PoultryBatch.objects.filter(pk=self.batch.pk).update(status=BatchStatus.CLOSED)
        response = self.complete(line['id'])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['detail'], "Ce bâtiment n'a pas de bande active.")
        self.assertEqual(self.on_hand(), 150)

    def test_a_line_is_not_completable_on_a_day_it_is_not_due(self):
        # Vaccine on day 7 only. The UI never offers it on day 1, but the endpoint takes any date.
        [line] = self.save_protocol(self.feed_line(from_value=7, until_end=False, to_value=7, what='Vaccin Gumboro'))
        response = self.complete(line['id'])
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("n'est pas prévue", response.data['detail'])
        self.assertEqual(self.on_hand(), 150)
        self.assertFalse(TaskCompletion.objects.exists())

    def test_a_timed_line_needs_its_slot(self):
        # Two feedings a day are two occurrences. Without a slot id the endpoint filed a third,
        # untimed one and deducted the stock for it while both real feedings stayed outstanding.
        [line] = self.save_protocol(self.feed_line(time_slots=[
            {'start_time': '07:00', 'end_time': '08:00'}, {'start_time': '16:00', 'end_time': '17:00'},
        ]))
        response = self.complete(line['id'])
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('créneau', response.data['detail'])
        self.assertEqual(self.on_hand(), 150)

    def test_editing_the_protocol_after_completion_keeps_the_completion_and_the_deduction(self):
        [line] = self.save_protocol(self.feed_line())
        self.complete(line['id'])
        self.save_protocol(self.feed_line(id=line['id'], what='Aliment démarrage (modifié)'))
        [task] = [t for t in self.tasks() if t['id'] == str(line['id'])]
        self.assertTrue(task['done'])
        self.assertEqual(self.complete(line['id']).data['status'], 'already_done')
        self.assertEqual(self.on_hand(), 110)


class ConcurrentCompletionTests(TransactionTestCase):
    """Two phones tapping "Marquer comme fait" at the same moment — real transactions, real
    row locks. Exactly one completion and one deduction must survive."""

    def setUp(self):
        self.farm, self.admin, self.worker, self.house, self.batch, self.item = build_farm('concurrence')
        feeding = ProtocolCategory.objects.get(house=self.house, label='Alimentation')
        self.line = ProtocolTemplate.objects.create(
            house=self.house, category=feeding, from_value=1, until_end=True, what='Aliment',
            stock_item=self.item, quantity_per_day=40,
        )

    def test_simultaneous_taps_deduct_once(self):
        barrier = threading.Barrier(4)
        statuses = []

        def tap():
            client = APIClient()
            client.force_authenticate(user=self.worker)
            try:
                barrier.wait()
                response = client.post(f'/api/houses/{self.house.house_code}/tasks-now/{self.line.id}/complete/', {}, format='json')
                statuses.append(response.status_code)
            finally:
                connection.close()

        threads = [threading.Thread(target=tap) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(TaskCompletion.objects.filter(protocol_template=self.line).count(), 1)
        self.assertEqual(StockMovement.objects.filter(item=self.item, movement_type=MovementType.OUT).count(), 1)
        self.assertNotIn(500, statuses, statuses)
        self.assertEqual(sorted(statuses).count(201), 1, statuses)
