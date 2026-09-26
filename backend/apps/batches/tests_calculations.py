"""Boundaries of apps.batches.calculations: mortality, FCR, weeks, the growth curve, the farm
health tiers and the working-capital estimate.

Logs are created with water = 2 x feed: a DailyLog save runs the water/feed deviation check
(normal range 1.6-2.2), and an accidental alert would change the farm-health tier under test.
"""
import datetime as dt
from decimal import Decimal

from django.test import TestCase

from apps.alerts.models import Alert, AlertRule, AlertRuleType, AlertStatus, TriggerMode
from apps.batches import calculations as calc
from apps.batches.models import BatchStatus, DailyLog, PoultryBatch, ProductionType
from apps.core.models import Farm
from apps.finance.models import Expense, ExpenseCategory, ProductType, Sale
from apps.houses.models import PoultryHouse

START = dt.date(2026, 1, 1)


class BatchCalcBase(TestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Bandes')
        self._houses = 0

    def batch(self, initial=1000, start=START, status=BatchStatus.ACTIVE):
        self._houses += 1
        house = PoultryHouse.objects.create(
            house_code=f'H-CALC-{self.farm.id}-{self._houses}', farm=self.farm,
            name=f'Bâtiment {self._houses}', max_capacity=5000,
        )
        return PoultryBatch.objects.create(
            batch_code=f'B-CALC-{self.farm.id}-{self._houses}', house=house,
            production_type=ProductionType.BROILER, initial_count=initial, start_date=start, status=status,
        )

    def log(self, batch, day, mortality=0, feed=0.0, weight=None):
        return DailyLog.objects.create(
            batch=batch, log_date=batch.start_date + dt.timedelta(days=day), mortality=mortality,
            feed_consumed_kg=feed, water_consumed_l=feed * 2, avg_sample_weight=weight,
        )


class MortalityTests(BatchCalcBase):
    def test_zero_initial_count_is_zero_not_an_error(self):
        self.assertEqual(calc.mortality_pct(self.batch(initial=0)), 0.0)

    def test_no_logs_is_zero(self):
        self.assertEqual(calc.mortality_pct(self.batch()), 0.0)

    def test_sums_every_day_and_rounds_to_two_decimals(self):
        b = self.batch(initial=300)
        self.log(b, 0, mortality=1)
        self.assertEqual(calc.mortality_pct(b), 0.33)
        self.log(b, 3, mortality=14)
        self.assertEqual(calc.mortality_pct(b), 5.0)


class FcrTests(BatchCalcBase):
    def test_none_without_a_sample_weight(self):
        b = self.batch()
        self.log(b, 0, feed=100)
        self.assertIsNone(calc.feed_conversion_ratio(b))

    def test_a_zero_weight_is_not_a_weighing(self):
        b = self.batch()
        self.log(b, 0, feed=100, weight=0)
        self.assertIsNone(calc.feed_conversion_ratio(b))

    def test_none_when_no_bird_is_left(self):
        b = self.batch(initial=10)
        self.log(b, 0, mortality=10, feed=5, weight=1.0)
        self.assertIsNone(calc.feed_conversion_ratio(b))

    def test_total_feed_over_current_flock_times_latest_weight(self):
        b = self.batch(initial=100)
        self.log(b, 0, feed=100, weight=0.5)
        self.log(b, 7, feed=100, weight=1.0)
        self.log(b, 8, feed=40)          # no weighing that day: the latest weight stays 1.0
        self.assertEqual(calc.feed_conversion_ratio(b), 2.4)

    def test_up_to_date_excludes_later_feed_and_weighings(self):
        b = self.batch(initial=100)
        self.log(b, 0, feed=100, weight=0.5)
        self.log(b, 7, feed=500, weight=2.0)
        self.assertEqual(calc.feed_conversion_ratio(b, up_to_date=START), 2.0)

    def test_a_past_week_uses_the_flock_alive_then_not_today(self):
        # Week 1: 100 kg of feed for 100 birds weighing 0.5 kg -> FCR 2.0. Birds that die in a
        # later week must not shrink week 1's flock after the fact (it read 4.0 with 50 birds).
        b = self.batch(initial=100)
        self.log(b, 0, feed=100, weight=0.5)
        self.log(b, 10, mortality=50)
        self.assertEqual(calc.feed_conversion_ratio(b, up_to_date=START), 2.0)
        # The current, undated FCR still uses today's flock.
        self.assertEqual(calc.feed_conversion_ratio(b), 4.0)


class WeekTests(BatchCalcBase):
    def test_week_one_is_the_first_seven_days(self):
        b = self.batch()
        self.assertEqual(calc.week_number(b, START), 1)
        self.assertEqual(calc.week_number(b, START + dt.timedelta(days=6)), 1)
        self.assertEqual(calc.week_number(b, START + dt.timedelta(days=7)), 2)

    def test_weekly_kpi_groups_sorts_and_takes_the_latest_weight_of_each_week(self):
        b = self.batch(initial=200)
        self.log(b, 8, mortality=2, feed=10, weight=0.9)
        self.log(b, 1, mortality=4, feed=10, weight=0.3)
        self.log(b, 5, feed=10, weight=0.4)
        weeks = calc.weekly_kpi(b)['weeks']
        self.assertEqual([w['week'] for w in weeks], [1, 2])
        self.assertEqual(weeks[0]['mortalityPct'], 2.0)
        self.assertEqual(weeks[0]['avgWeightKg'], 0.4)
        self.assertEqual(weeks[1]['mortalityPct'], 1.0)

    def test_weekly_kpi_with_zero_initial_count(self):
        b = self.batch(initial=0)
        self.log(b, 0)
        self.assertEqual(calc.weekly_kpi(b)['weeks'][0]['mortalityPct'], 0.0)


class GrowthCurveTests(BatchCalcBase):
    def test_points_are_zero_based_days_in_date_order(self):
        b = self.batch(initial=100)
        self.log(b, 3, mortality=10)
        self.log(b, 0, weight=0.05)
        points = calc.growth_curve(b)
        self.assertEqual([p['dayOfCycle'] for p in points], [0, 3])
        self.assertEqual(points[0]['weightKg'], 0.05)
        self.assertEqual([p['survivalPct'] for p in points], [100.0, 90.0])

    def test_survival_never_goes_below_zero(self):
        # More deaths than birds can reach the table through a direct write or a later
        # correction of an earlier day; the curve must floor at 0 %, not plot -20 %.
        b = self.batch(initial=10)
        self.log(b, 0, mortality=12)
        self.assertEqual(calc.growth_curve(b)[0]['survivalPct'], 0.0)

    def test_survival_is_none_without_an_initial_count(self):
        b = self.batch(initial=0)
        self.log(b, 0)
        self.assertIsNone(calc.growth_curve(b)[0]['survivalPct'])


class FarmHealthTests(BatchCalcBase):
    def open_alert(self, severity, status=AlertStatus.NEW):
        rule = AlertRule.objects.create(farm=self.farm, rule_type=AlertRuleType.LOW_STOCK, trigger_mode=TriggerMode.EVENT)
        return Alert.objects.create(rule=rule, message='test', severity=severity, status=status)

    def test_good_with_no_batch_and_no_alert(self):
        self.assertEqual(calc.farm_health_score(self.farm)['tier'], 'good')

    def test_mortality_exactly_at_the_weekly_limit_is_not_a_breach(self):
        b = self.batch(initial=100)
        self.log(b, 0, mortality=5)            # one week logged -> limit 5 / 1 = 5 %
        self.assertEqual(calc.farm_health_score(self.farm)['tier'], 'good')

    def test_mortality_just_above_the_weekly_limit_is_a_breach(self):
        b = self.batch(initial=1000)
        self.log(b, 0, mortality=51)           # 5.1 % > 5 %
        health = calc.farm_health_score(self.farm)
        self.assertEqual(health['tier'], 'watch')
        self.assertIn('mortalité', health['reason'])

    def test_fcr_exactly_at_the_upper_reference_is_not_a_breach(self):
        b = self.batch(initial=100)
        self.log(b, 0, feed=230, weight=1.0)   # FCR 2.30
        self.assertEqual(calc.farm_health_score(self.farm)['tier'], 'good')

    def test_fcr_just_above_the_upper_reference_is_a_breach(self):
        b = self.batch(initial=100)
        self.log(b, 0, feed=231, weight=1.0)   # FCR 2.31
        self.assertIn("consommation d'aliment", calc.farm_health_score(self.farm)['reason'])

    def test_one_batch_breaching_both_signals_is_critical(self):
        b = self.batch(initial=100)
        self.log(b, 0, mortality=6, feed=300, weight=1.0)
        self.assertEqual(calc.farm_health_score(self.farm)['tier'], 'critical')

    def test_closed_batches_are_ignored(self):
        b = self.batch(initial=100, status=BatchStatus.CLOSED)
        self.log(b, 0, mortality=50)
        self.assertEqual(calc.farm_health_score(self.farm)['tier'], 'good')

    def test_one_open_warning_alert_is_watch_and_resolved_ones_do_not_count(self):
        self.open_alert('warning', status=AlertStatus.RESOLVED)
        self.assertEqual(calc.farm_health_score(self.farm)['tier'], 'good')
        self.open_alert('warning')
        health = calc.farm_health_score(self.farm)
        self.assertEqual(health['tier'], 'watch')
        self.assertIn('1 alerte ouverte', health['reason'])

    def test_any_open_danger_alert_is_critical(self):
        self.open_alert('danger')
        self.assertEqual(calc.farm_health_score(self.farm)['tier'], 'critical')

    def test_plural_alert_wording(self):
        self.open_alert('warning')
        self.open_alert('warning')
        self.assertIn('2 alertes ouvertes', calc.farm_health_score(self.farm)['reason'])


class MoneyPerBatchTests(BatchCalcBase):
    def test_bfr_counts_rows_on_the_as_of_date_but_not_after(self):
        b = self.batch()
        day = dt.date(2026, 2, 1)
        Expense.objects.create(farm=self.farm, batch=b, category=ExpenseCategory.FEED, amount=Decimal('1000'), expense_date=day)
        Expense.objects.create(farm=self.farm, batch=b, category=ExpenseCategory.FEED, amount=Decimal('999'), expense_date=day + dt.timedelta(days=1))
        Sale.objects.create(farm=self.farm, batch=b, product_type=ProductType.BIRD, quantity=1, unit_price=Decimal('400'), sale_date=day)
        self.assertEqual(calc.bfr_estimate(b, day), Decimal('600'))

    def test_bfr_is_negative_when_sales_exceed_spending(self):
        b = self.batch()
        Sale.objects.create(farm=self.farm, batch=b, product_type=ProductType.BIRD, quantity=2, unit_price=Decimal('100'), sale_date=START)
        self.assertEqual(calc.bfr_estimate(b, START), Decimal('-200'))

    def test_closing_report_margins_and_unit_cost(self):
        b = self.batch(initial=100)
        self.log(b, 0, mortality=20)
        Expense.objects.create(farm=self.farm, batch=b, category=ExpenseCategory.FEED, amount=Decimal('800'), expense_date=START)
        Expense.objects.create(farm=self.farm, batch=b, category=ExpenseCategory.LABOR, amount=Decimal('300'), expense_date=START)
        Sale.objects.create(farm=self.farm, batch=b, product_type=ProductType.BIRD, quantity=80, unit_price=Decimal('20'), sale_date=START)
        report = calc.build_closing_report(b)
        self.assertEqual(report.revenue, Decimal('1600'))
        self.assertEqual(report.total_variable_cost, Decimal('800'))
        self.assertEqual(report.unit_cost_price, Decimal('10'))          # 800 / 80 birds left
        self.assertEqual(report.total_margin, Decimal('500'))            # 1600 - 800 - 300
        self.assertEqual(report.total_mortality_pct, 20.0)

    def test_closing_report_with_no_bird_left_has_no_unit_cost(self):
        b = self.batch(initial=10)
        self.log(b, 0, mortality=10)
        self.assertIsNone(calc.build_closing_report(b).unit_cost_price)
