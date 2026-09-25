"""Query counts that must not grow with the data.

The 2026-09-25 load test (a million birds, 20 000 employees — `manage.py seed_load_farm`,
`bench_load`) found screens issuing one or more queries per row: 403 for the stock list, 1 138 for
the "Bilan global" tree, 6 453 for one run of the scheduled-reminder task. Each test here measures
an endpoint at two sizes and requires the same number of queries, so a per-row query reintroduced
anywhere along the path fails here instead of on the farm.
"""
import datetime as dt
from datetime import time
from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.alerts.models import Alert, AlertRule, AlertRuleType, SmsMessage, TriggerMode
from apps.alerts.services import fire_scheduled_alerts
from apps.batches.models import BatchStatus, DailyLog, PoultryBatch, ProductionType
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.finance.models import Expense, OrderStatus, PurchaseOrder, Sale
from apps.houses.models import PoultryHouse
from apps.maintenance.models import EquipmentFault, UnusualCase
from apps.protocols.models import ProtocolCategory, ProtocolTemplate, ProtocolTimeSlot
from apps.protocols.services import expand_protocol_to_alert_rules
from apps.stock.models import MovementType, StockCategory, StockComposition, StockCompositionIngredient, StockItem, StockMovement


class ScalingBase(APITestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.farm = Farm.objects.create(name='Ferme échelle')
        self.admin = self.user(UserRole.ADMIN, 'admin')
        self.client.force_authenticate(self.admin)
        self.feed = StockCategory.objects.get(farm=self.farm, kind='FEED')
        self.houses = 0
        self.items = 0

    def user(self, role, tag=None):
        self.users = getattr(self, 'users', 0) + 1
        tag = tag or f'u{self.users}'
        user = User.objects.create_user(
            email=f'{tag}@echelle.local', password='x', name=f'Employé {tag}', role=role, farm=self.farm,
            phone=f'+23760000{self.users:04d}',
        )
        create_role_profile(user)
        return user

    def item(self, quantity_in=100, quantity_out=10):
        self.items += 1
        item = StockItem.objects.create(
            item_code=f'SC-{self.items:03d}', farm=self.farm, category=self.feed, name=f'Article {self.items:03d}',
            unit='kg', alert_threshold=50, unit_price=Decimal('100'),
        )
        StockMovement.objects.create(item=item, movement_type=MovementType.IN, quantity=quantity_in, movement_date=self.today)
        StockMovement.objects.create(item=item, movement_type=MovementType.OUT, quantity=quantity_out, movement_date=self.today)
        return item

    def house_with_batch(self, days=10, slots=((6, 30), (17, 30))):
        self.houses += 1
        house = PoultryHouse.objects.create(
            house_code=f'H-SC-{self.houses:03d}', farm=self.farm, name=f'Bâtiment {self.houses}', max_capacity=1000,
        )
        batch = PoultryBatch.objects.create(
            batch_code=f'B-SC-{self.houses:03d}', house=house, name=f'Bande {self.houses}',
            production_type=ProductionType.BROILER, initial_count=1000,
            start_date=self.today - dt.timedelta(days=days), status=BatchStatus.ACTIVE,
        )
        for back in range(days):
            DailyLog.objects.create(
                batch=batch, log_date=self.today - dt.timedelta(days=back + 1), mortality=2,
                feed_consumed_kg=50, water_consumed_l=100, avg_sample_weight=0.5 if back % 7 == 0 else None,
            )
        category = ProtocolCategory.objects.filter(house=house).first()
        line = ProtocolTemplate.objects.create(house=house, category=category, from_value=1, until_end=True, what='Aliment')
        for hh, mm in slots:
            ProtocolTimeSlot.objects.create(protocol_line=line, start_time=time(hh, mm), end_time=time(hh + 1, mm))
        return house, batch, line

    def count(self, url):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200, getattr(response, 'data', None))
        return len(ctx.captured_queries)

    def assertFlat(self, url, grow):
        """Same query count for `url` before and after `grow()` adds more rows."""
        before = self.count(url)
        grow()
        self.assertEqual(self.count(url), before, f'{url}: query count grew with the data')


class StockScalingTests(ScalingBase):
    def test_stock_list_badge_and_compositions(self):
        first = self.item()
        composition = StockComposition.objects.create(farm=self.farm, name='Formule', output_item=first)
        StockCompositionIngredient.objects.create(composition=composition, item=first, quantity=1)

        def grow():
            for _ in range(4):
                StockCompositionIngredient.objects.create(composition=composition, item=self.item(), quantity=1)

        for url in (f'/api/farms/{self.farm.id}/stock-items/', '/api/stock-items/low-count/',
                    f'/api/farms/{self.farm.id}/stock-compositions/'):
            with self.subTest(url=url):
                self.assertFlat(url, grow)

    def test_list_quantities_match_a_fresh_read(self):
        from apps.stock.calculations import current_quantity

        low = self.item(quantity_in=60, quantity_out=20)  # 40 on hand, threshold 50 -> low
        self.item()
        rows = {r['item_code']: r['current_quantity'] for r in self.client.get(f'/api/farms/{self.farm.id}/stock-items/').data['items']}
        for item in StockItem.objects.filter(farm=self.farm):
            self.assertEqual(rows[item.item_code], current_quantity(item))
        self.assertEqual(rows[low.item_code], 40)
        self.assertEqual(self.client.get('/api/stock-items/low-count/').data['count'], 1)
        # The list keeps its order (category, then name) despite the aggregating query.
        self.assertEqual(list(rows), sorted(rows, key=lambda code: StockItem.objects.get(pk=code).name))


class BatchScalingTests(ScalingBase):
    def test_health_overview_batches_and_curves(self):
        self.house_with_batch()

        def grow():
            for _ in range(3):
                self.house_with_batch()

        for url in ('/api/batches/health-score/', '/api/farm/overview/', '/api/batches/?status=ACTIVE',
                    '/api/batches/growth-curves/', '/api/tasks/upcoming/'):
            with self.subTest(url=url):
                self.assertFlat(url, grow)

    def test_listed_flock_is_initial_count_minus_logged_mortality(self):
        _, batch, _ = self.house_with_batch(days=10)
        row = self.client.get('/api/batches/?status=ACTIVE').data['results'][0]
        self.assertEqual(row['current_count'], 1000 - 10 * 2)
        self.assertEqual(row['current_count'], PoultryBatch.objects.get(pk=batch.pk).current_count)

    def test_weekly_kpi_reads_the_logs_once(self):
        _, batch, _ = self.house_with_batch(days=8)
        before = self.count(f'/api/batches/{batch.batch_code}/kpi/weekly/')
        for back in range(8, 30):
            DailyLog.objects.create(batch=batch, log_date=self.today - dt.timedelta(days=back + 1), mortality=1, feed_consumed_kg=40)
        self.assertEqual(self.count(f'/api/batches/{batch.batch_code}/kpi/weekly/'), before)


class ListScalingTests(ScalingBase):
    def test_alerts_incidents_faults_orders(self):
        house, batch, _ = self.house_with_batch()
        rule = AlertRule.objects.create(farm=self.farm, rule_type=AlertRuleType.LOW_STOCK, trigger_mode=TriggerMode.EVENT)
        item = self.item()
        n = {'i': 0}

        def add():
            n['i'] += 1
            i = n['i']
            Alert.objects.create(rule=rule, batch=batch, message=f'Alerte {i}')
            worker = self.user(UserRole.WORKER)
            UnusualCase.objects.create(case_code=f'UC-{i}', batch=batch, worker=worker, case_description='Cas')
            EquipmentFault.objects.create(fault_code=f'EF-{i}', house=house, technician=worker, fault_description='Panne')
            PurchaseOrder.objects.create(order_code=f'PO-SC-{i}', farm=self.farm, item=item, quantity=1, amount=Decimal('10'))

        add()
        for url in ('/api/alerts/', '/api/alerts/?open=1', '/api/unusual-cases/?resolved=false',
                    '/api/equipment-faults/?status=OPEN', '/api/purchase-orders/'):
            with self.subTest(url=url):
                self.assertFlat(url, lambda: [add() for _ in range(4)])


class FinanceScalingTests(ScalingBase):
    def add_rows(self, n, start_day=0):
        item = self.item()
        for i in range(n):
            day = self.today - dt.timedelta(days=start_day + i % 20)
            Sale.objects.create(farm=self.farm, product_type='BIRD', quantity=1, unit_price=Decimal('100'),
                                total_amount=Decimal('100'), sale_date=day)
            Expense.objects.create(farm=self.farm, category='FEED', amount=Decimal('30'), expense_date=day)
            order = PurchaseOrder.objects.create(order_code=f'PO-F-{start_day}-{i}', farm=self.farm, item=item,
                                                 quantity=1, amount=Decimal('20'), status=OrderStatus.RECEIVED)
            PurchaseOrder.objects.filter(pk=order.pk).update(order_date=day)

    def test_summaries_do_not_read_row_by_row(self):
        self.add_rows(3)
        for url in ('/api/finance/summary/', '/api/finance/purchases-evolution/', '/api/finance/sales-evolution/',
                    '/api/finance/expense-categories/', '/api/finance/transactions/?page=1&type=all'):
            with self.subTest(url=url):
                self.assertFlat(url, lambda: self.add_rows(6, start_day=len(url)))

    def test_ledger_pages_are_the_full_merge_cut_into_twenties(self):
        self.add_rows(17)  # 51 rows over 20 dates: ties across all three sources
        pages, page = [], 1
        while True:
            data = self.client.get(f'/api/finance/transactions/?page={page}&type=all').data
            pages += data['results']
            if page * data['pageSize'] >= data['count']:
                break
            page += 1
        self.assertEqual(data['count'], 51)
        self.assertEqual(len(pages), 51)
        self.assertEqual(len({r['id'] for r in pages}), 51)  # no row twice, none skipped
        dates = [str(r['date']) for r in pages]
        self.assertEqual(dates, sorted(dates, reverse=True))


class WorkforceScalingTests(ScalingBase):
    def test_my_tasks_only_computes_the_workers_houses(self):
        worker = self.user(UserRole.WORKER, 'awa')
        _, _, line = self.house_with_batch()
        line.assignees.add(worker)
        self.client.force_authenticate(worker)
        tasks = self.client.get('/api/tasks/mine/').data
        self.assertEqual(len(tasks), 2)  # one per slot
        self.assertTrue(all(t['what'] == 'Aliment' for t in tasks))

        def grow():
            for _ in range(3):
                _, _, other = self.house_with_batch()
                other.assignees.add(self.user(UserRole.WORKER))

        self.assertFlat('/api/tasks/mine/', grow)
        self.assertEqual(len(self.client.get('/api/tasks/mine/').data), 2)

    def test_weighing_assignment_alone_still_lists_the_house(self):
        worker = self.user(UserRole.WORKER, 'ben')
        _, batch, _ = self.house_with_batch(days=7)
        batch.weighing_frequency = 'WEEK'
        batch.save()
        rule = AlertRule.objects.create(
            farm=self.farm, rule_type=AlertRuleType.WEIGHING_REMINDER, trigger_mode=TriggerMode.SCHEDULED, batch=batch,
        )
        rule.assignees.add(worker)
        self.client.force_authenticate(worker)
        whats = [t['what'] for t in self.client.get('/api/tasks/mine/').data]
        self.assertEqual(len(whats), 1, whats)


class ScheduledReminderScalingTests(ScalingBase):
    def setUp(self):
        super().setUp()
        _, self.batch, self.line = self.house_with_batch(slots=((6, 30),))
        expand_protocol_to_alert_rules(self.batch)
        local = timezone.get_current_timezone()
        self.now = dt.datetime.combine(self.today, time(6, 30), tzinfo=local)

    def fire(self):
        with CaptureQueriesContext(connection) as ctx:
            alerts = fire_scheduled_alerts(now=self.now)
        return alerts, len(ctx.captured_queries)

    def test_one_sms_per_assignee_in_constant_queries(self):
        self.line.assignees.add(*[self.user(UserRole.WORKER) for _ in range(2)])
        alerts, small = self.fire()
        self.assertEqual(SmsMessage.objects.filter(alert=alerts[0]).count(), 2)

        Alert.objects.all().delete()
        SmsMessage.objects.all().delete()
        self.line.assignees.add(*[self.user(UserRole.WORKER) for _ in range(6)])
        alerts, large = self.fire()
        self.assertEqual(SmsMessage.objects.filter(alert=alerts[0]).count(), 8)
        self.assertEqual(large, small)

    def test_an_sms_already_sent_today_is_not_created_again(self):
        self.line.assignees.add(*[self.user(UserRole.WORKER) for _ in range(3)])
        self.fire()
        self.assertEqual(SmsMessage.objects.count(), 3)
        # The 10-minute "already fired" guard is what normally stops a re-run; take it away and
        # the idempotency key alone must still refuse a second SMS for the same person and day.
        Alert.objects.update(triggered_at=self.now - dt.timedelta(hours=1))
        alerts, _ = self.fire()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(SmsMessage.objects.count(), 3)
        self.assertEqual(SmsMessage.objects.filter(alert=alerts[0]).count(), 0)
