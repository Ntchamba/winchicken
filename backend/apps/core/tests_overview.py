"""Threshold logic for the "Bilan global" tree (apps.core.overview).

Each branch is exercised at its boundaries rather than with one happy-path fixture: the whole
point of the module is where a status flips, so that is what these pin. The core node is
tested independently of the branches (it is pure "worst of three"), including the rule that
`drivers` names which branch set the status.
"""
import datetime as dt
from decimal import Decimal
from unittest.mock import patch

from rest_framework.test import APITestCase

from apps.batches.models import BatchStatus, DailyLog, PoultryBatch, ProductionType
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.core.overview import (
    CASH_WATCH_FLOOR, STOCK_LOW_COUNT_FOR_CRITICAL, farm_overview, finance_branch,
    health_branch, stock_branch,
)
from apps.finance.models import Expense, ExpenseCategory, ProductType, Sale
from apps.houses.models import PoultryHouse
from apps.stock.models import MovementType, StockCategory, StockItem, StockMovement


class OverviewTestBase(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Overview')
        self.user = User.objects.create_user(
            email='admin@overview-test.local', password='x', name='U',
            role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.user)
        self.feed = StockCategory.objects.get(farm=self.farm, kind='FEED')

    def _item(self, name, threshold, quantity):
        self._seq = getattr(self, '_seq', 0) + 1
        item = StockItem.objects.create(
            item_code=f'FEE-{self.farm.id}-{self._seq:03d}', farm=self.farm, category=self.feed,
            name=name, unit='kg', alert_threshold=threshold, unit_price=Decimal('100.00'),
        )
        if quantity:
            StockMovement.objects.create(
                item=item, movement_type=MovementType.IN, quantity=quantity,
                movement_date=dt.date.today(),
            )
        return item

    def _sale(self, amount, days_ago=1):
        return Sale.objects.create(
            farm=self.farm, product_type=ProductType.BIRD, quantity=1,
            unit_price=Decimal(str(amount)), sale_date=dt.date.today() - dt.timedelta(days=days_ago),
        )

    def _expense(self, amount, days_ago=1):
        return Expense.objects.create(
            farm=self.farm, category=ExpenseCategory.FEED, amount=Decimal(str(amount)),
            expense_date=dt.date.today() - dt.timedelta(days=days_ago),
        )


class StockBranchThresholdTests(OverviewTestBase):
    def test_no_articles_at_all_is_good(self):
        branch = stock_branch(self.farm)
        self.assertEqual(branch['tier'], 'good')
        self.assertEqual(branch['value'], 0)

    def test_comfortably_above_threshold_is_good(self):
        self._item('Provende', threshold=100, quantity=500)
        self.assertEqual(stock_branch(self.farm)['tier'], 'good')

    def test_exactly_at_the_threshold_counts_as_low(self):
        # The rule is "at or under", so the boundary itself must already warn.
        self._item('Provende', threshold=100, quantity=100)
        branch = stock_branch(self.farm)
        self.assertEqual(branch['tier'], 'watch')
        self.assertIn('Provende', branch['lowItems'])

    def test_one_article_just_under_threshold_is_watch(self):
        self._item('Provende', threshold=100, quantity=99)
        self.assertEqual(stock_branch(self.farm)['tier'], 'watch')

    def test_low_count_one_below_the_critical_count_is_still_watch(self):
        for i in range(STOCK_LOW_COUNT_FOR_CRITICAL - 1):
            self._item(f'Article{i}', threshold=100, quantity=50)
        self.assertEqual(stock_branch(self.farm)['tier'], 'watch')

    def test_reaching_the_critical_low_count_is_critical(self):
        for i in range(STOCK_LOW_COUNT_FOR_CRITICAL):
            self._item(f'Article{i}', threshold=100, quantity=50)
        branch = stock_branch(self.farm)
        self.assertEqual(branch['tier'], 'critical')
        self.assertIn('sous leur seuil', branch['message'])

    def test_a_single_stock_out_is_critical_on_its_own(self):
        # One empty article outranks the count rule — running out is worse than being low.
        self._item('Provende', threshold=100, quantity=0)
        branch = stock_branch(self.farm)
        self.assertEqual(branch['tier'], 'critical')
        self.assertIn('épuisé', branch['message'])

    def test_an_article_with_no_threshold_set_is_only_low_when_empty(self):
        self._item('Sans seuil', threshold=0, quantity=5)
        self.assertEqual(stock_branch(self.farm)['tier'], 'good')


class FinanceBranchThresholdTests(OverviewTestBase):
    def test_healthy_cash_is_good(self):
        self._sale(CASH_WATCH_FLOOR * 2)
        branch = finance_branch(self.farm)
        self.assertEqual(branch['tier'], 'good')
        self.assertEqual(branch['message'], 'La ferme va bien financièrement')

    def test_cash_just_under_the_floor_is_watch(self):
        self._sale(CASH_WATCH_FLOOR - 1)
        branch = finance_branch(self.farm)
        self.assertEqual(branch['tier'], 'watch')
        self.assertEqual(branch['message'], 'Trésorerie faible')

    def test_cash_exactly_at_the_floor_is_good(self):
        # `cash < CASH_WATCH_FLOOR` — the floor itself is acceptable.
        self._sale(CASH_WATCH_FLOOR)
        self.assertEqual(finance_branch(self.farm)['tier'], 'good')

    def test_negative_cash_is_critical(self):
        self._expense(50_000)
        branch = finance_branch(self.farm)
        self.assertEqual(branch['tier'], 'critical')
        self.assertEqual(branch['message'], 'Trésorerie négative')

    def test_negative_cash_outranks_the_watch_floor(self):
        self._sale(10_000)
        self._expense(80_000)
        self.assertEqual(finance_branch(self.farm)['tier'], 'critical')

    def test_a_month_with_expenses_and_no_sales_is_watch_even_on_healthy_cash(self):
        # Comfortable cash, but nothing sold in the latest month — worth flagging.
        self._sale(CASH_WATCH_FLOOR * 3, days_ago=200)
        self._expense(1_000, days_ago=0)
        branch = finance_branch(self.farm)
        self.assertEqual(branch['tier'], 'watch')
        self.assertEqual(branch['message'], 'Aucune vente le mois dernier')

    def test_revenue_reported_is_the_six_month_total(self):
        self._sale(100_000, days_ago=1)
        self._sale(50_000, days_ago=20)
        self.assertEqual(finance_branch(self.farm)['value'], 150_000)

    def test_empty_farm_reports_zero_without_failing(self):
        branch = finance_branch(self.farm)
        self.assertEqual(branch['value'], 0)
        self.assertEqual(branch['cash'], 0)


class HealthBranchTests(OverviewTestBase):
    def _batch(self, count=100):
        house = PoultryHouse.objects.create(
            house_code=f'H-{self.farm.id}-001', farm=self.farm, name='Poulailler', max_capacity=count,
        )
        return PoultryBatch.objects.create(
            batch_code='BATCH-OV-1', house=house, name='Bande', production_type=ProductionType.BROILER,
            initial_count=count, start_date=dt.date.today() - dt.timedelta(days=10),
            planned_end_date=dt.date.today() + dt.timedelta(days=40), status=BatchStatus.ACTIVE,
        )

    def test_tier_comes_from_the_shared_farm_health_score(self):
        # The branch must not re-derive health — it reports whatever that function decided.
        with patch('apps.core.overview.farm_health_score', return_value={'tier': 'critical', 'reason': 'raison test'}):
            branch = health_branch(self.farm)
        self.assertEqual(branch['tier'], 'critical')
        self.assertEqual(branch['message'], 'raison test')

    def test_bird_count_sums_active_batches_and_subtracts_mortality(self):
        batch = self._batch(count=100)
        DailyLog.objects.create(batch=batch, log_date=dt.date.today(), mortality=12)
        branch = health_branch(self.farm)
        self.assertEqual(branch['value'], 88)
        self.assertIn('88', branch['valueLabel'])

    def test_closed_batches_are_not_counted(self):
        batch = self._batch(count=100)
        batch.status = BatchStatus.CLOSED
        batch.save()
        self.assertEqual(health_branch(self.farm)['value'], 0)


class CoreNodeTests(OverviewTestBase):
    """The core is pure "worst of three" — tested by driving the branches directly."""

    def _overview_with(self, finance, stock, health):
        make = lambda tier: {'tier': tier, 'message': '', 'value': 0, 'valueLabel': ''}
        with patch('apps.core.overview.finance_branch', return_value=make(finance)), \
             patch('apps.core.overview.stock_branch', return_value=make(stock)), \
             patch('apps.core.overview.health_branch', return_value=make(health)):
            return farm_overview(self.farm)

    def test_all_good_is_good(self):
        core = self._overview_with('good', 'good', 'good')['core']
        self.assertEqual(core['tier'], 'good')
        self.assertEqual(core['label'], 'Ferme en bonne santé')
        self.assertEqual(core['drivers'], [])

    def test_a_single_watch_pulls_the_core_to_watch(self):
        core = self._overview_with('good', 'watch', 'good')['core']
        self.assertEqual(core['tier'], 'watch')
        self.assertEqual(core['label'], 'Attention requise')
        self.assertEqual(core['drivers'], ['stock'])

    def test_a_single_critical_outranks_two_goods(self):
        core = self._overview_with('good', 'good', 'critical')['core']
        self.assertEqual(core['tier'], 'critical')
        self.assertEqual(core['label'], 'Intervention urgente')
        self.assertEqual(core['drivers'], ['health'])

    def test_critical_outranks_watch(self):
        core = self._overview_with('critical', 'watch', 'watch')['core']
        self.assertEqual(core['tier'], 'critical')
        self.assertEqual(core['drivers'], ['finance'])

    def test_every_branch_at_the_worst_tier_is_named_as_a_driver(self):
        core = self._overview_with('critical', 'critical', 'good')['core']
        self.assertCountEqual(core['drivers'], ['finance', 'stock'])

    def test_thresholds_are_reported_so_the_ui_can_explain_itself(self):
        data = self._overview_with('good', 'good', 'good')
        self.assertEqual(data['thresholds']['cashWatchFloor'], CASH_WATCH_FLOOR)
        self.assertEqual(data['thresholds']['stockLowCountForCritical'], STOCK_LOW_COUNT_FOR_CRITICAL)


class OverviewEndpointTests(OverviewTestBase):
    def test_endpoint_returns_the_three_branches_and_a_core(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get('/api/farm/overview/')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertCountEqual(resp.data['branches'].keys(), ['finance', 'stock', 'health'])
        self.assertIn(resp.data['core']['tier'], ('good', 'watch', 'critical'))

    def test_endpoint_requires_authentication(self):
        self.assertEqual(self.client.get('/api/farm/overview/').status_code, 401)
