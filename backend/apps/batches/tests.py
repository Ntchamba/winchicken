from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APITestCase

from apps.batches.calculations import feed_conversion_ratio
from apps.batches.models import BatchStatus, DailyLog, PoultryBatch, ProductionType
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse


class SingleActiveBatchConstraintTests(TestCase):
    """`PoultryBatch.Meta.constraints`' `one_active_batch_per_house` (docs/deviations.md
    Part 15, Part B) — the sanitary-void principle: a house must be fully vacated (its batch
    closed) before a new one can start there. Enforced at the DB level, not just serializer
    validation, so this asserts the constraint itself, not a view."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Test')
        self.house = PoultryHouse.objects.create(house_code='H-T-1', farm=self.farm, name='Bâtiment', max_capacity=1000)

    def test_second_active_batch_in_same_house_is_rejected(self):
        PoultryBatch.objects.create(
            batch_code='BATCH-T-1', house=self.house, production_type=ProductionType.BROILER,
            initial_count=500, start_date='2026-01-01', status=BatchStatus.ACTIVE,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            PoultryBatch.objects.create(
                batch_code='BATCH-T-2', house=self.house, production_type=ProductionType.BROILER,
                initial_count=500, start_date='2026-01-02', status=BatchStatus.ACTIVE,
            )

    def test_second_batch_allowed_once_first_is_closed(self):
        first = PoultryBatch.objects.create(
            batch_code='BATCH-T-3', house=self.house, production_type=ProductionType.BROILER,
            initial_count=500, start_date='2026-01-01', status=BatchStatus.ACTIVE,
        )
        first.status = BatchStatus.CLOSED
        first.save()
        second = PoultryBatch.objects.create(
            batch_code='BATCH-T-4', house=self.house, production_type=ProductionType.BROILER,
            initial_count=500, start_date='2026-01-02', status=BatchStatus.ACTIVE,
        )
        self.assertEqual(second.status, BatchStatus.ACTIVE)


class CurrentCountTests(TestCase):
    """`PoultryBatch.current_count` (docs/deviations.md Part 10 item 87, Part 15) — computed
    property (`initial_count` minus `SUM(DailyLog.mortality)`), not a stored/decremented
    column. Covers the "edit an already-logged day's mortality" correction case that motivated
    the switch away from a stored field in the first place."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Test')
        self.house = PoultryHouse.objects.create(house_code='H-T-2', farm=self.farm, name='Bâtiment', max_capacity=1000)
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-T-5', house=self.house, production_type=ProductionType.BROILER,
            initial_count=1000, start_date='2026-01-01',
        )

    def test_current_count_derived_from_summed_mortality(self):
        DailyLog.objects.create(batch=self.batch, log_date='2026-01-02', mortality=5)
        DailyLog.objects.create(batch=self.batch, log_date='2026-01-03', mortality=3)
        self.assertEqual(self.batch.current_count, 992)

    def test_correcting_an_already_logged_day_updates_current_count(self):
        log = DailyLog.objects.create(batch=self.batch, log_date='2026-01-02', mortality=5)
        self.assertEqual(self.batch.current_count, 995)

        log.mortality = 2  # correction, e.g. a data-entry mistake caught the next day
        log.save()
        self.assertEqual(self.batch.current_count, 998)

    def test_django_admin_style_direct_save_is_still_reflected(self):
        # The exact gap the computed-property switch closed (item 87): a direct .save() that
        # bypasses every app write path (record_quick_entry, DailyLogListCreateView) must still
        # be reflected, since current_count is derived fresh on every read, not decremented by
        # whichever code path happened to write the row.
        DailyLog.objects.create(batch=self.batch, log_date='2026-01-02', mortality=10)
        self.assertEqual(PoultryBatch.objects.get(pk=self.batch.pk).current_count, 990)


class FeedConversionRatioTests(TestCase):
    """`apps.batches.calculations.feed_conversion_ratio` (docs/deviations.md Part 15).

    Note on this test's origin: the task that requested it assumed FCR is computed from
    `StockMovement`, "not from any deprecated field." Checked against the actual implementation
    before writing anything — `feed_conversion_ratio` (this module, implementation-detail spec
    5.1) computes `SUM(DailyLog.feed_consumed_kg) / (current_count * latest avg_sample_weight)`;
    there is no `StockMovement`-based FCR anywhere in this codebase, and `feed_consumed_kg` is
    not deprecated — it's the one and only spec-mandated source. This test asserts the actual,
    correct, spec-compliant behavior rather than a `StockMovement`-based calculation that would
    have been a regression against the documented spec to introduce.
    """

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Test')
        self.house = PoultryHouse.objects.create(house_code='H-T-3', farm=self.farm, name='Bâtiment', max_capacity=1000)
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-T-6', house=self.house, production_type=ProductionType.BROILER,
            initial_count=1000, start_date='2026-01-01',
        )

    def test_fcr_uses_summed_feed_and_latest_sample_weight(self):
        DailyLog.objects.create(batch=self.batch, log_date='2026-01-02', feed_consumed_kg=100, avg_sample_weight=0.5)
        DailyLog.objects.create(batch=self.batch, log_date='2026-01-03', feed_consumed_kg=150, avg_sample_weight=0.6)
        # total_feed=250, current_count=1000 (no mortality logged), latest weight=0.6
        self.assertEqual(feed_conversion_ratio(self.batch), round(250 / (1000 * 0.6), 2))

    def test_fcr_is_none_without_a_sample_weight_yet(self):
        DailyLog.objects.create(batch=self.batch, log_date='2026-01-02', feed_consumed_kg=100)
        self.assertIsNone(feed_conversion_ratio(self.batch))


class FarmHealthScoreTests(APITestCase):
    """GET /api/batches/health-score/ (docs/deviations.md Part 16, Part A) — the exact
    verification scenario the task asked for: trigger a real alert, confirm the tier degrades,
    resolve it, confirm it reverts to "good"."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Santé Test')
        self.admin = User.objects.create_user(email='admin@health-test.local', password='x', name='Admin', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(self.admin)
        self.house = PoultryHouse.objects.create(house_code='H-HS-1', farm=self.farm, name='Bâtiment Santé', max_capacity=1000)
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-HS-1', house=self.house, production_type=ProductionType.BROILER,
            initial_count=1000, start_date=date.today() - timedelta(days=7),
        )
        self.client.force_authenticate(user=self.admin)
        self.url = '/api/batches/health-score/'

    def test_good_with_no_breaches_and_no_alerts(self):
        response = self.client.get(self.url)
        self.assertEqual(response.data['tier'], 'good')

    def test_open_danger_alert_forces_critical_and_resolving_reverts_to_good(self):
        from apps.alerts.services import trigger_alert
        alert = trigger_alert(farm=self.farm, rule_type='LOW_STOCK', message='Aliment sous le seuil', severity='danger')

        response = self.client.get(self.url)
        self.assertEqual(response.data['tier'], 'critical')
        self.assertIn('alerte', response.data['reason'])

        alert.status = 'RESOLVED'
        alert.save()
        response = self.client.get(self.url)
        self.assertEqual(response.data['tier'], 'good')

    def test_single_warning_alert_forces_watch_not_critical(self):
        from apps.alerts.services import trigger_alert
        trigger_alert(farm=self.farm, rule_type='CONSUMPTION_DEVIATION', message='Ratio hors norme', severity='warning', batch=self.batch)
        response = self.client.get(self.url)
        self.assertEqual(response.data['tier'], 'watch')

    def test_mortality_breach_reuses_the_same_threshold_as_the_weekly_chart(self):
        # Week 1 mortality far above the pro-rata share of MORTALITY_REFERENCE_RANGE[1]=5%.
        DailyLog.objects.create(batch=self.batch, log_date=date.today() - timedelta(days=6), mortality=100)
        response = self.client.get(self.url)
        self.assertEqual(response.data['tier'], 'watch')
        self.assertIn('mortalité', response.data['reason'])


class DailyLogQuickEntryPermissionTests(APITestCase):
    """`DailyLogQuickEntryView`/`DailyLogListCreateView`'s POST branch (docs/deviations.md,
    2026-08-27 bugfix) — `IsFarmerOrWorker` wrongly excluded Admin and Farm Manager from
    recording weight/mortality, a role-check regression, not an intentional restriction (unlike
    e.g. `CanEditHouseProtocol` or finance's `IsAdminOrFarmManager`). Covers every role so a
    future accidental narrowing shows up here instead of only in manual QA."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Permission Test')
        self.house = PoultryHouse.objects.create(house_code='H-P-1', farm=self.farm, name='Bâtiment', max_capacity=1000)
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-P-1', house=self.house, production_type=ProductionType.BROILER,
            initial_count=500, start_date=date.today() - timedelta(days=10),
        )
        self.url = f'/api/batches/{self.batch.batch_code}/daily-logs/quick-entry/'

    def _user(self, role, email):
        user = User.objects.create_user(email=email, password='x', name='Test User', role=role, farm=self.farm)
        create_role_profile(user)
        return user

    def test_admin_can_record_mortality(self):
        self.client.force_authenticate(user=self._user(UserRole.ADMIN, 'admin@perm-test.local'))
        response = self.client.put(self.url, {'date': str(date.today()), 'mortality': 2}, format='json')
        self.assertEqual(response.status_code, 200)

    def test_farm_manager_can_record_mortality(self):
        self.client.force_authenticate(user=self._user(UserRole.FARM_MANAGER, 'fm@perm-test.local'))
        response = self.client.put(self.url, {'date': str(date.today()), 'mortality': 2}, format='json')
        self.assertEqual(response.status_code, 200)

    def test_farmer_can_record_mortality(self):
        self.client.force_authenticate(user=self._user(UserRole.FARMER, 'farmer@perm-test.local'))
        response = self.client.put(self.url, {'date': str(date.today()), 'mortality': 2}, format='json')
        self.assertEqual(response.status_code, 200)

    def test_worker_can_record_mortality(self):
        self.client.force_authenticate(user=self._user(UserRole.WORKER, 'worker@perm-test.local'))
        response = self.client.put(self.url, {'date': str(date.today()), 'mortality': 2}, format='json')
        self.assertEqual(response.status_code, 200)

    def test_cashier_is_still_forbidden(self):
        self.client.force_authenticate(user=self._user(UserRole.CASHIER, 'cashier@perm-test.local'))
        response = self.client.put(self.url, {'date': str(date.today()), 'mortality': 2}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_technician_is_still_forbidden(self):
        self.client.force_authenticate(user=self._user(UserRole.TECHNICIAN, 'tech@perm-test.local'))
        response = self.client.put(self.url, {'date': str(date.today()), 'mortality': 2}, format='json')
        self.assertEqual(response.status_code, 403)





class SensitiveBatchActionPermissionTests(APITestCase):
    """Server-side role gating on the two irreversible batch actions — DELETE
    /api/batches/{code}/ and PATCH /api/batches/{code}/close/ — both `IsAdminOrFarmManager`.

    NOTE: this codebase does *not* require password re-verification for batch close/delete
    (only `POST /api/farm/reset/` does). They are gated by role + a typed frontend confirmation
    dialog, per the view docstrings. There is therefore no wrong-password path to test here.
    """

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Sensible')
        self.house = PoultryHouse.objects.create(house_code='H-S-1', farm=self.farm, name='Bâtiment', max_capacity=1000)
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-S-1', house=self.house, production_type=ProductionType.BROILER,
            initial_count=500, start_date=date.today() - timedelta(days=10),
        )

    def _user(self, role, email):
        user = User.objects.create_user(email=email, password='x', name='U', role=role, farm=self.farm)
        create_role_profile(user)
        return user

    def test_worker_cannot_delete_a_batch(self):
        self.client.force_authenticate(user=self._user(UserRole.WORKER, 'w@s.local'))
        resp = self.client.delete(f'/api/batches/{self.batch.batch_code}/')
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(PoultryBatch.objects.filter(pk=self.batch.pk).exists())

    def test_farmer_cannot_delete_a_batch(self):
        self.client.force_authenticate(user=self._user(UserRole.FARMER, 'f@s.local'))
        resp = self.client.delete(f'/api/batches/{self.batch.batch_code}/')
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_delete_a_batch(self):
        self.client.force_authenticate(user=self._user(UserRole.ADMIN, 'a@s.local'))
        resp = self.client.delete(f'/api/batches/{self.batch.batch_code}/')
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(PoultryBatch.objects.filter(pk=self.batch.pk).exists())

    def test_worker_cannot_close_a_batch(self):
        self.client.force_authenticate(user=self._user(UserRole.WORKER, 'w2@s.local'))
        resp = self.client.patch(f'/api/batches/{self.batch.batch_code}/close/')
        self.assertEqual(resp.status_code, 403)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, BatchStatus.ACTIVE)

    def test_farm_manager_can_close_a_batch(self):
        self.client.force_authenticate(user=self._user(UserRole.FARM_MANAGER, 'fm@s.local'))
        resp = self.client.patch(f'/api/batches/{self.batch.batch_code}/close/')
        self.assertEqual(resp.status_code, 200)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.status, BatchStatus.CLOSED)

    def test_closing_an_already_closed_batch_is_rejected(self):
        self.batch.status = BatchStatus.CLOSED
        self.batch.save(update_fields=['status'])
        self.client.force_authenticate(user=self._user(UserRole.ADMIN, 'a2@s.local'))
        resp = self.client.patch(f'/api/batches/{self.batch.batch_code}/close/')
        self.assertEqual(resp.status_code, 400)
