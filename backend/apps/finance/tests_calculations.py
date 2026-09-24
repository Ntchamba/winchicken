"""Boundaries of the money calculations in apps.finance.calculations.

Bucketing is pinned at the edges where dates are easy to get wrong (ISO weeks across New Year,
month ends, the first day of a window); the ratio helpers at zero, equality and sign changes;
ROI and the category breakdown on which rows fall inside the window. "Today" is frozen per test
so a run on any date checks the same thing.
"""
import datetime as dt
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.core.models import Farm
from apps.finance import calculations as calc
from apps.finance.models import Expense, ExpenseCategory, OrderStatus, ProductType, PurchaseOrder, Sale
from apps.stock.models import StockCategory, StockItem


def frozen(day):
    return patch('apps.finance.calculations.timezone.localdate', return_value=day)


class BucketTests(TestCase):
    """Pure date helpers behind the Ventes/Achats charts (no database)."""

    def test_week_buckets_are_eight_mondays_ending_with_the_current_week(self):
        with frozen(dt.date(2026, 9, 24)):  # a Thursday
            starts, unit = calc._bucket_starts('week')
        self.assertEqual(unit, 'week')
        self.assertEqual(len(starts), 8)
        self.assertEqual(starts[-1], dt.date(2026, 9, 21))
        self.assertTrue(all(s.weekday() == 0 for s in starts))
        self.assertEqual(starts[0], dt.date(2026, 8, 3))

    def test_week_bucket_on_a_monday_starts_that_same_day(self):
        with frozen(dt.date(2026, 9, 21)):
            starts, _ = calc._bucket_starts('week')
        self.assertEqual(starts[-1], dt.date(2026, 9, 21))

    def test_iso_week_label_uses_the_iso_year_across_new_year(self):
        # Monday 2024-12-30 is ISO week 1 of 2025. '%Y-W%V' labelled it "2024-W01" — the same
        # label as the real first week of 2024, so two different weeks shared a chart bucket.
        self.assertEqual(calc._bucket_label(dt.date(2024, 12, 30), 'week'), '2025-W01')
        self.assertEqual(calc._bucket_label(dt.date(2024, 1, 1), 'week'), '2024-W01')
        # And the last ISO week of a year whose Monday falls in December stays in that year.
        self.assertEqual(calc._bucket_label(dt.date(2024, 12, 23), 'week'), '2024-W52')

    def test_week_labels_stay_unique_and_ordered_across_new_year(self):
        with frozen(dt.date(2025, 1, 15)):
            starts, unit = calc._bucket_starts('week')
        labels = [calc._bucket_label(s, unit) for s in starts]
        self.assertEqual(len(set(labels)), len(labels))
        self.assertEqual(labels, sorted(labels))

    def test_year_buckets_are_five_january_firsts_ending_this_year(self):
        with frozen(dt.date(2026, 1, 1)):
            starts, unit = calc._bucket_starts('year')
        self.assertEqual(unit, 'year')
        self.assertEqual(starts, [dt.date(y, 1, 1) for y in range(2022, 2027)])
        self.assertEqual(calc._bucket_end(starts[-1], 'year'), dt.date(2027, 1, 1))
        self.assertEqual(calc._bucket_label(starts[-1], 'year'), '2026')

    def test_month_buckets_from_a_31st_do_not_skip_a_month(self):
        with frozen(dt.date(2026, 3, 31)):
            starts, unit = calc._bucket_starts('month')
        self.assertEqual(unit, 'month')
        self.assertEqual(len(starts), 12)
        self.assertEqual(starts[0], dt.date(2025, 4, 1))
        self.assertEqual(starts[-1], dt.date(2026, 3, 1))
        self.assertEqual(len({(s.year, s.month) for s in starts}), 12)

    def test_unknown_period_falls_back_to_months(self):
        with frozen(dt.date(2026, 9, 24)):
            _, unit = calc._bucket_starts('fortnight')
        self.assertEqual(unit, 'month')

    def test_bucket_ends_are_exclusive_next_starts(self):
        self.assertEqual(calc._bucket_end(dt.date(2026, 12, 1), 'month'), dt.date(2027, 1, 1))
        self.assertEqual(calc._bucket_end(dt.date(2026, 12, 28), 'week'), dt.date(2027, 1, 4))


class RatioHelperTests(TestCase):
    """series_trend / break_even_quantity / safety_margin_pct — pure functions."""

    def test_series_trend_needs_two_buckets(self):
        self.assertEqual(calc.series_trend([]), 'flat')
        self.assertEqual(calc.series_trend([{'total': 999.0}]), 'flat')

    def test_series_trend_boundaries(self):
        self.assertEqual(calc.series_trend([{'total': 100.0}, {'total': 100.0}]), 'flat')
        self.assertEqual(calc.series_trend([{'total': 100.0}, {'total': 100.01}]), 'up')
        self.assertEqual(calc.series_trend([{'total': 100.0}, {'total': 99.99}]), 'down')
        self.assertEqual(calc.series_trend([{'total': 0.0}, {'total': 0.0}]), 'flat')
        # Only the last two buckets count.
        self.assertEqual(calc.series_trend([{'total': 500.0}, {'total': 1.0}, {'total': 2.0}]), 'up')

    def test_break_even_quantity(self):
        self.assertEqual(calc.break_even_quantity(1000, 150, 100), 20)
        self.assertEqual(calc.break_even_quantity(0, 150, 100), 0)
        # Price equal to the variable cost: no break-even exists.
        self.assertIsNone(calc.break_even_quantity(1000, 100, 100))
        # Selling below the variable cost: every sale loses money, so there is no break-even
        # quantity either — a negative "quantity" would be a fabricated figure.
        self.assertIsNone(calc.break_even_quantity(1000, 90, 100))

    def test_safety_margin_pct(self):
        self.assertIsNone(calc.safety_margin_pct(0, 20))
        self.assertIsNone(calc.safety_margin_pct(None, 20))
        self.assertIsNone(calc.safety_margin_pct(100, None))
        self.assertEqual(calc.safety_margin_pct(100, 100), 0.0)
        self.assertEqual(calc.safety_margin_pct(100, 80), 20.0)
        # Below break-even is a meaningful negative margin, not an error.
        self.assertEqual(calc.safety_margin_pct(80, 100), -25.0)
        self.assertEqual(calc.safety_margin_pct(100, 0), 100.0)


class WindowedTotalsTests(TestCase):
    """ROI and the category breakdown: which rows fall inside the window, and the zero cases."""

    TODAY = dt.date(2026, 9, 24)  # '6m' window starts 2026-04-01

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Calculs')
        self._seq = 0

    def _item(self, kind):
        self._seq += 1
        category = StockCategory.objects.get(farm=self.farm, kind=kind)
        return StockItem.objects.create(
            item_code=f'CAL-{self.farm.id}-{self._seq:03d}', farm=self.farm, category=category,
            name=f'Article {self._seq}', unit='unité', alert_threshold=0, unit_price=Decimal('1'),
        )

    def _order(self, kind, amount, day, status=OrderStatus.RECEIVED):
        self._seq += 1
        order = PurchaseOrder.objects.create(
            order_code=f'PO-CAL-{self._seq:03d}', farm=self.farm, item=self._item(kind),
            quantity=1, amount=Decimal(str(amount)), status=status,
        )
        # order_date is auto_now_add: set it after creation.
        PurchaseOrder.objects.filter(pk=order.pk).update(order_date=day)
        return order

    def _expense(self, amount, day, category=ExpenseCategory.FEED):
        return Expense.objects.create(farm=self.farm, category=category, amount=Decimal(str(amount)), expense_date=day)

    def _sale(self, amount, day):
        return Sale.objects.create(
            farm=self.farm, product_type=ProductType.BIRD, quantity=1,
            unit_price=Decimal(str(amount)), sale_date=day,
        )

    def roi(self):
        with frozen(self.TODAY):
            return calc.roi_forecast_pct(self.farm, '6m')

    def breakdown(self):
        with frozen(self.TODAY):
            return {c['category']: c['amountPct'] for c in calc.expense_category_breakdown(self.farm, '6m')['categories']}

    # --- ROI -------------------------------------------------------------------------------

    def test_roi_is_none_without_equipment_investment(self):
        self._sale(5000, self.TODAY)
        self.assertIsNone(self.roi())

    def test_roi_ignores_pending_and_out_of_window_equipment(self):
        self._order('EQUIPMENT', 1000, self.TODAY, status=OrderStatus.PENDING)
        self._order('EQUIPMENT', 1000, dt.date(2026, 3, 31))  # the day before the window
        self.assertIsNone(self.roi())

    def test_roi_counts_equipment_received_on_the_first_day_of_the_window(self):
        self._order('EQUIPMENT', 1000, dt.date(2026, 4, 1))
        self._sale(1500, self.TODAY)
        self._expense(500, self.TODAY)
        self.assertEqual(self.roi(), 100.0)

    def test_roi_margin_subtracts_received_supply_orders_like_every_other_expense_total(self):
        # Feed bought through a purchase order is an expense in the monthly summary, Achats and
        # the category breakdown; ROI's margin must see it too, or it overstates the return.
        self._order('EQUIPMENT', 1000, self.TODAY)
        self._sale(1500, self.TODAY)
        self._order('FEED', 500, self.TODAY)
        self.assertEqual(self.roi(), 100.0)

    def test_roi_does_not_count_the_investment_itself_as_an_expense(self):
        self._order('EQUIPMENT', 1000, self.TODAY)
        self._sale(1000, self.TODAY)
        self.assertEqual(self.roi(), 100.0)

    def test_roi_can_be_negative(self):
        self._order('EQUIPMENT', 1000, self.TODAY)
        self._expense(1500, self.TODAY)
        self.assertEqual(self.roi(), -150.0)

    # --- Category breakdown -----------------------------------------------------------------

    def test_breakdown_is_empty_with_no_expenses(self):
        self.assertEqual(self.breakdown(), {})

    def test_breakdown_single_category_is_one_hundred_percent(self):
        self._expense(750, self.TODAY, ExpenseCategory.VETERINARY)
        self.assertEqual(self.breakdown(), {'VETERINARY': 100.0})

    def test_breakdown_window_boundary(self):
        self._expense(100, dt.date(2026, 4, 1), ExpenseCategory.FEED)     # first day: in
        self._expense(900, dt.date(2026, 3, 31), ExpenseCategory.LABOR)   # day before: out
        self.assertEqual(self.breakdown(), {'FEED': 100.0})

    def test_breakdown_folds_received_orders_by_item_kind_and_skips_pending(self):
        self._expense(100, self.TODAY, ExpenseCategory.FEED)
        self._order('FEED', 100, self.TODAY)                                # FEED
        self._order('EQUIPMENT', 200, self.TODAY)                           # -> DEPRECIATION
        self._order('VETERINARY', 999, self.TODAY, status=OrderStatus.PENDING)
        self.assertEqual(self.breakdown(), {'FEED': 50.0, 'DEPRECIATION': 50.0})

    # --- Trend direction ----------------------------------------------------------------------

    def test_finance_trend_down_when_this_month_is_below_last(self):
        self._sale(500, dt.date(2026, 8, 10))
        self._sale(100, dt.date(2026, 9, 10))
        with frozen(self.TODAY):
            trend = calc.finance_trend_direction(self.farm, '6m')
        self.assertEqual(trend['revenueTrend'], 'down')
        self.assertEqual(trend['expenseTrend'], 'flat')
