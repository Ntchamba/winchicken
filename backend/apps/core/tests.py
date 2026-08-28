from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.alerts.models import AlertRule, AlertRuleType, TriggerMode
from apps.batches.models import DailyLog, PoultryBatch, ProductionType
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse
from apps.protocols.models import ProtocolCategory, ProtocolTemplate
from apps.stock.models import ItemCategory, StockCategory, StockItem


class FarmCreateValidationTests(APITestCase):
    """POST /api/farm/create/ — field-level error messages (docs/deviations.md Part 13). No
    farm exists yet in this isolated test DB, so these exercise the actual success/validation
    paths that can't be exercised against the real dev stack once a farm has been created there
    (this is a single-farm app — see FactoryResetTests for the same constraint elsewhere).
    """

    def setUp(self):
        self.url = reverse('farm-create')
        self.valid_payload = {
            'admin_name': 'Amina Ndoye', 'civility': 'MME', 'email': 'amina@winchicken.test',
            'password': 'S3curePass!', 'farm_name': 'Ferme Ndoye',
        }

    def test_succeeds_with_valid_payload(self):
        response = self.client.post(self.url, self.valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', response.data)
        self.assertEqual(Farm.objects.count(), 1)

    def test_weak_password_returns_specific_field_error(self):
        payload = {**self.valid_payload, 'password': 'short'}
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)
        self.assertEqual(Farm.objects.count(), 0)

    def test_duplicate_email_returns_specific_field_error(self):
        User.objects.create_user(
            email='amina@winchicken.test', password='x', name='Existing', role=UserRole.WORKER,
        )
        response = self.client.post(self.url, self.valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)
        self.assertIn('email', response.data['email'][0].lower())

    def test_existing_farm_returns_409_with_detail(self):
        Farm.objects.create(name='Une autre ferme')
        response = self.client.post(self.url, self.valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('detail', response.data)


class LoginTests(APITestCase):
    """POST /api/auth/login/ (docs/deviations.md Part 15, Part B)."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Login Test')
        self.admin = User.objects.create_user(
            email='admin@login-test.local', password='S3curePass!', name='Admin', role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.admin)
        self.worker = User.objects.create_user(
            email='worker@login-test.local', password='S3curePass!', name='Worker', role=UserRole.WORKER, farm=self.farm,
        )
        create_role_profile(self.worker)
        self.url = reverse('auth-login')

    def test_admin_login_succeeds(self):
        response = self.client.post(self.url, {'email': 'admin@login-test.local', 'password': 'S3curePass!'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertEqual(response.data['role'], 'ADMIN')

    def test_employee_login_succeeds(self):
        response = self.client.post(self.url, {'email': 'worker@login-test.local', 'password': 'S3curePass!'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['role'], 'WORKER')

    def test_is_configured_reflects_farm_state(self):
        response = self.client.post(self.url, {'email': 'admin@login-test.local', 'password': 'S3curePass!'}, format='json')
        self.assertFalse(response.data['is_configured'])

        house = PoultryHouse.objects.create(house_code='H-LOGIN-1', farm=self.farm, name='Bâtiment', max_capacity=100)
        category = ProtocolCategory.objects.create(house=house, label='Alimentation', icon='Soup')
        ProtocolTemplate.objects.create(house=house, category=category, from_value=1, what='Test')
        StockItem.objects.create(item_code='FEE-LOGIN-1', farm=self.farm, category=StockCategory.objects.get(farm=self.farm, kind='FEED'), name='Aliment', unit='kg')

        response = self.client.post(self.url, {'email': 'admin@login-test.local', 'password': 'S3curePass!'}, format='json')
        self.assertTrue(response.data['is_configured'])

    def test_wrong_password_rejected_with_specific_detail(self):
        response = self.client.post(self.url, {'email': 'admin@login-test.local', 'password': 'wrong'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('detail', response.data)


class FactoryResetTests(APITestCase):
    """POST /api/farm/reset/ (docs/deviations.md Part 12) — one row from every farm-scoped
    table, proving the CASCADE chain from Farm actually reaches all of them, not just the
    ones with a direct FK.
    """

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Test Reset')
        self.admin = User.objects.create_user(
            email='admin@test.local', password='Sup3rSecret!', name='Admin Test',
            role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.admin)
        self.worker = User.objects.create_user(
            email='worker@test.local', password='Sup3rSecret!', name='Worker Test',
            role=UserRole.WORKER, farm=self.farm,
        )
        create_role_profile(self.worker)

        self.house = PoultryHouse.objects.create(
            house_code='H-TEST-1', farm=self.farm, name='Bâtiment test', max_capacity=1000,
        )
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-TEST-1', house=self.house, production_type=ProductionType.BROILER,
            initial_count=500, start_date='2026-01-01',
        )
        DailyLog.objects.create(batch=self.batch, log_date='2026-01-02', mortality=2)
        StockItem.objects.create(
            item_code='FEE-TEST-1', farm=self.farm, category=StockCategory.objects.get(farm=self.farm, kind='FEED'), name='Aliment test', unit='kg',
        )
        AlertRule.objects.create(farm=self.farm, rule_type=AlertRuleType.LOW_STOCK, trigger_mode=TriggerMode.EVENT)

        self.url = reverse('farm-reset')

    def test_wipes_every_farm_scoped_table(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(self.url, {'password': 'Sup3rSecret!'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Farm.objects.count(), 0)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(PoultryHouse.objects.count(), 0)
        self.assertEqual(PoultryBatch.objects.count(), 0)
        self.assertEqual(DailyLog.objects.count(), 0)
        self.assertEqual(StockItem.objects.count(), 0)
        self.assertEqual(AlertRule.objects.count(), 0)
        # ProtocolCategory rows are seeded by a post_save signal on PoultryHouse, reachable only
        # transitively (ProtocolCategory -> PoultryHouse -> Farm) — proves the cascade goes deep,
        # not just one FK hop.
        self.assertEqual(ProtocolCategory.objects.count(), 0)

        exists_response = self.client.get(reverse('farm-exists'))
        self.assertFalse(exists_response.data['exists'])

    def test_wrong_password_is_rejected_and_nothing_is_deleted(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(self.url, {'password': 'wrong-password'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Farm.objects.count(), 1)
        self.assertEqual(User.objects.count(), 2)

    def test_non_admin_forbidden_server_side(self):
        self.client.force_authenticate(user=self.worker)
        response = self.client.post(self.url, {'password': 'Sup3rSecret!'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Farm.objects.count(), 1)

    def test_unauthenticated_rejected(self):
        response = self.client.post(self.url, {'password': 'Sup3rSecret!'}, format='json')
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))
        self.assertEqual(Farm.objects.count(), 1)


class FactoryResetLoggingTests(TestCase):
    """The external, outside-the-database audit trail — the one piece of evidence that survives
    the reset it documents. Exercises `apps.core.services.factory_reset_farm` directly rather
    than through the view, since only the write to the real filesystem log matters here.
    """

    def test_writes_plain_text_log_entry_before_deleting(self):
        from apps.core.services import factory_reset_farm

        farm = Farm.objects.create(name='Ferme Journal Test')
        admin = User.objects.create_user(
            email='journal-admin@test.local', password='x', name='Journal Admin',
            role=UserRole.ADMIN, farm=farm,
        )
        create_role_profile(admin)

        log_path = Path(settings.LOGS_DIR) / 'factory_reset.log'
        before = log_path.read_text() if log_path.exists() else ''

        factory_reset_farm(farm, admin)

        after = log_path.read_text()
        new_content = after[len(before):]
        self.assertIn('Ferme Journal Test', new_content)
        self.assertIn('journal-admin@test.local', new_content)
        self.assertEqual(Farm.objects.count(), 0)


class AuditLogTests(APITestCase):
    """GET /api/audit-log/ and the record_audit_log call sites (docs/deviations.md Part 15,
    Part C) — a real consequential action (creating an employee) produces a real, readable
    entry, visible only to Administrateur."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Audit Test')
        self.admin = User.objects.create_user(
            email='admin@audit-test.local', password='x', name='Admin Audit', role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.admin)
        self.worker = User.objects.create_user(
            email='worker@audit-test.local', password='x', name='Worker Audit', role=UserRole.WORKER, farm=self.farm,
        )
        create_role_profile(self.worker)

    def test_a_real_action_produces_a_readable_audit_entry_visible_to_admin_only(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(reverse('employee-list'), {
            'name': 'Nouvel Employé', 'civility': 'MME', 'email': 'nouvel@audit-test.local', 'role': 'FARMER', 'password': 'S3curePass!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        list_response = self.client.get(reverse('audit-log'))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        results = list_response.data['results'] if 'results' in list_response.data else list_response.data
        entry = next(e for e in results if e['action'] == 'employee.created')
        self.assertEqual(entry['user_name_snapshot'], 'Admin Audit')
        self.assertIn('Nouvel Employé', entry['target_description'])

        self.client.force_authenticate(user=self.worker)
        forbidden = self.client.get(reverse('audit-log'))
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

    def test_action_filter_narrows_results(self):
        self.client.force_authenticate(user=self.admin)
        self.client.post(reverse('employee-list'), {
            'name': 'A', 'civility': 'M', 'email': 'a@audit-test.local', 'role': 'FARMER', 'password': 'S3curePass!',
        }, format='json')
        response = self.client.get(reverse('audit-log'), {'action': 'farm.reset'})
        results = response.data['results'] if 'results' in response.data else response.data
        self.assertEqual(len(results), 0)  # no farm.reset happened in this test


class BackupRestoreTests(TransactionTestCase):
    """`python manage.py backup_db` / `restore_db` (docs/deviations.md Part 15) — real pg_dump/
    pg_restore subprocess calls against Django's isolated test database, never the real dev
    database (same caution as FactoryResetTests). `TransactionTestCase`, not `TestCase`:
    pg_dump connects as its own separate process/connection and only sees *committed* data —
    `TestCase`'s per-test transaction wrapping (always rolled back, never committed) would make
    it see an empty database regardless of what a test just created.

    `BACKUP_DIR` in both command modules is patched to a throwaway temp directory for every
    test here — never the real `backend/backups/`.
    """

    def setUp(self):
        import shutil
        import tempfile
        self._tmp_dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self._tmp_dir, ignore_errors=True))
        from unittest import mock
        self._patchers = [
            mock.patch('apps.core.management.commands.backup_db.BACKUP_DIR', self._tmp_dir),
            mock.patch('apps.core.management.commands.restore_db.BACKUP_DIR', self._tmp_dir),
        ]
        for p in self._patchers:
            p.start()
            self.addCleanup(p.stop)

    def test_backup_writes_a_real_restorable_dump(self):
        call_command('backup_db', stdout=StringIO())
        dumps = list(self._tmp_dir.glob('winchicken-*.dump'))
        self.assertEqual(len(dumps), 1)
        self.assertGreater(dumps[0].stat().st_size, 0)

    def test_backup_prunes_beyond_retention(self):
        import time
        # 8 pre-existing dumps, oldest first (default retention is 7 — no BACKUP_RETENTION_COUNT
        # override in this environment, confirmed against backend/.env.example's documented default).
        for i in range(8):
            (self._tmp_dir / f'winchicken-fake{i}.dump').write_bytes(b'fake')
            time.sleep(0.01)
        call_command('backup_db', stdout=StringIO())  # 9th, and the newest
        remaining = list(self._tmp_dir.glob('winchicken-*.dump'))
        self.assertEqual(len(remaining), 7)

    def test_restore_round_trip_actually_restores_data(self):
        Farm.objects.create(name='Ferme Backup Test')
        call_command('backup_db', stdout=StringIO())
        dump_file = next(self._tmp_dir.glob('winchicken-*.dump'))

        Farm.objects.all().delete()
        self.assertEqual(Farm.objects.count(), 0)

        call_command('restore_db', dump_file.name, '--yes', stdout=StringIO())

        self.assertTrue(Farm.objects.filter(name='Ferme Backup Test').exists())

    def test_restore_without_yes_aborts_on_decline(self):
        from unittest import mock
        Farm.objects.create(name='Ferme Non Restaurée')
        call_command('backup_db', stdout=StringIO())
        dump_file = next(self._tmp_dir.glob('winchicken-*.dump'))
        Farm.objects.all().delete()

        with mock.patch('builtins.input', return_value='no'):
            call_command('restore_db', dump_file.name, stdout=StringIO())

        self.assertEqual(Farm.objects.count(), 0)  # declined — nothing restored


class EmployeePayrollListViewTests(APITestCase):
    """GET /api/employees/payroll/ — Salaires module (2026-08-27, Finances restructure Part D).
    Farm Manager has no access to the general /api/employees/ endpoint (IsAdminOrSecondaryAdmin);
    this narrow id/name/hourly_rate list is their equivalent read surface for rate editing in
    SalairesSection.jsx."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Payroll Test')
        self.admin = User.objects.create_user(
            email='admin@payroll-test.local', password='x', name='Admin', role=UserRole.ADMIN, farm=self.farm,
        )
        self.manager = User.objects.create_user(
            email='manager@payroll-test.local', password='x', name='Manager', role=UserRole.FARM_MANAGER, farm=self.farm,
        )
        self.worker = User.objects.create_user(
            email='worker@payroll-test.local', password='x', name='Worker', role=UserRole.WORKER,
            farm=self.farm, hourly_rate='12.50',
        )
        self.url = reverse('employee-payroll-list')

    def test_admin_sees_employee_rates(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data['results']
        names = {row['name'] for row in results}
        self.assertIn('Worker', names)
        self.assertNotIn('Admin', names)  # excludes the requester's own account
        worker_row = next(row for row in results if row['name'] == 'Worker')
        self.assertEqual(worker_row['hourly_rate'], '12.50')

    def test_farm_manager_also_allowed(self):
        self.client.force_authenticate(self.manager)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_other_roles_forbidden(self):
        self.client.force_authenticate(self.worker)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
