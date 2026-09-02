from io import BytesIO, StringIO
from pathlib import Path
from unittest import mock

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


class PreLoginFarmResetTests(APITestCase):
    """POST /api/farm/reset/request/ + /confirm/ — the unauthenticated factory-reset flow
    reachable from /login (docs/deviations.md Part 21). Verifies the credential gate leaks
    nothing (same generic error for wrong password, unknown email, and non-Administrateur), and
    that the two-step token exchange still ends in the same full CASCADE wipe as the
    session-based FarmResetView.
    """

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Test Prélogin')
        self.admin = User.objects.create_user(
            email='admin@prelogin.local', password='Sup3rSecret!', name='Admin Prélogin',
            role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.admin)
        self.worker = User.objects.create_user(
            email='worker@prelogin.local', password='Sup3rSecret!', name='Worker Prélogin',
            role=UserRole.WORKER, farm=self.farm,
        )
        create_role_profile(self.worker)
        self.house = PoultryHouse.objects.create(
            house_code='H-PRELOGIN-1', farm=self.farm, name='Bâtiment prélogin', max_capacity=1000,
        )
        self.request_url = reverse('farm-reset-request')
        self.confirm_url = reverse('farm-reset-confirm')

    def _valid_token(self):
        response = self.client.post(
            self.request_url, {'email': 'admin@prelogin.local', 'password': 'Sup3rSecret!'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.data['token']

    def test_request_returns_token_and_farm_name_for_admin(self):
        response = self.client.post(
            self.request_url, {'email': 'admin@prelogin.local', 'password': 'Sup3rSecret!'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['token'])
        self.assertEqual(response.data['farm_name'], 'Ferme Test Prélogin')

    def test_request_wrong_password_generic_error_no_token(self):
        response = self.client.post(
            self.request_url, {'email': 'admin@prelogin.local', 'password': 'nope'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn('token', response.data)
        self.assertEqual(response.data['non_field_errors'], ['Identifiants invalides.'])

    def test_request_non_admin_rejected_without_revealing_role(self):
        response = self.client.post(
            self.request_url, {'email': 'worker@prelogin.local', 'password': 'Sup3rSecret!'}, format='json',
        )
        # Same 400 + same message as a wrong password — a 403 here would confirm the account exists.
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['non_field_errors'], ['Identifiants invalides.'])

    def test_request_unknown_email_same_generic_error(self):
        response = self.client.post(
            self.request_url, {'email': 'ghost@prelogin.local', 'password': 'Sup3rSecret!'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['non_field_errors'], ['Identifiants invalides.'])

    def test_confirm_with_valid_token_and_exact_name_wipes_farm(self):
        token = self._valid_token()
        response = self.client.post(
            self.confirm_url, {'token': token, 'farm_name': 'Ferme Test Prélogin'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Farm.objects.count(), 0)
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(PoultryHouse.objects.count(), 0)
        self.assertFalse(self.client.get(reverse('farm-exists')).data['exists'])

    def test_confirm_wrong_farm_name_rejected_nothing_deleted(self):
        token = self._valid_token()
        response = self.client.post(
            self.confirm_url, {'token': token, 'farm_name': 'Mauvais Nom'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Farm.objects.count(), 1)
        self.assertEqual(User.objects.count(), 2)

    def test_confirm_tampered_token_rejected_nothing_deleted(self):
        token = self._valid_token()
        response = self.client.post(
            self.confirm_url, {'token': token + 'x', 'farm_name': 'Ferme Test Prélogin'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Farm.objects.count(), 1)

    def test_confirm_foreign_salt_token_rejected(self):
        from django.core import signing
        forged = signing.dumps({'uid': self.admin.id}, salt='some.other.salt')
        response = self.client.post(
            self.confirm_url, {'token': forged, 'farm_name': 'Ferme Test Prélogin'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Farm.objects.count(), 1)

    def test_confirm_expired_token_rejected(self):
        with mock.patch('apps.core.serializers.PRELOGIN_RESET_MAX_AGE', -1):
            token = self._valid_token()
            response = self.client.post(
                self.confirm_url, {'token': token, 'farm_name': 'Ferme Test Prélogin'}, format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Farm.objects.count(), 1)

    def test_request_endpoint_needs_no_authentication(self):
        # No force_authenticate anywhere in this class — the flow's whole point is working
        # without a session; this asserts the endpoint itself doesn't 401/403 an anonymous call.
        response = self.client.post(
            self.request_url, {'email': 'admin@prelogin.local', 'password': 'Sup3rSecret!'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class EmployeeXlsxImportTests(APITestCase):
    """Excel import for Employees — update-or-create by Email, never deletes, never resets an
    existing password, generates + returns a temp password per new account (docs/excel-import.md)."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Employés Import')
        self.admin = User.objects.create_user(email='admin@emp-imp.local', password='AdminPass1!', name='Admin',
                                              role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(self.admin)
        self.client.force_authenticate(user=self.admin)
        self.existing = User.objects.create_user(email='marie@emp-imp.local', password='MariePass1!', name='Marie D.',
                                                 role=UserRole.WORKER, civility='MME', farm=self.farm)
        create_role_profile(self.existing)

    @staticmethod
    def _xlsx(rows, headers=None):
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active
        ws.append(headers or ['Nom', 'Email', 'Rôle', 'Civilité', 'Taux horaire'])
        for r in rows:
            ws.append(r)
        buf = BytesIO(); wb.save(buf); buf.seek(0); buf.name = 'e.xlsx'
        return buf

    def _upload(self, buf):
        return self.client.post('/api/employees/import-xlsx/', {'file': buf}, format='multipart')

    def test_template_downloads_without_auth(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get('/api/employees/import-template.xlsx')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('attachment', resp['Content-Disposition'])

    def test_existing_updates_role_password_unchanged_new_gets_temp_password(self):
        resp = self._upload(self._xlsx([
            ['Marie Dupont', 'marie@emp-imp.local', 'Fermier', 'Mme', 1500],   # existing -> role WORKER->FARMER
            ['Jean Kouassi', 'jean@emp-imp.local', 'Gérant de ferme', 'M.', ''],  # new
        ]))
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual((resp.data['updated'], resp.data['created']), (1, 1))
        self.assertEqual(resp.data['skipped'], [])

        self.existing.refresh_from_db()
        self.assertEqual(self.existing.role, UserRole.FARMER)
        self.assertEqual(self.existing.name, 'Marie Dupont')
        self.assertEqual(str(self.existing.hourly_rate), '1500.00')
        self.assertTrue(self.existing.check_password('MariePass1!'))  # password NOT reset

        new = User.objects.get(email='jean@emp-imp.local')
        self.assertEqual(new.role, UserRole.FARM_MANAGER)
        acc = resp.data['newAccounts']
        self.assertEqual(len(acc), 1)
        self.assertEqual(acc[0]['email'], 'jean@emp-imp.local')
        self.assertTrue(acc[0]['password'])
        self.assertTrue(new.check_password(acc[0]['password']))  # the returned temp password works

    def test_invalid_role_is_skipped_specifically_not_guessed(self):
        resp = self._upload(self._xlsx([
            ['Bad Role', 'bad@emp-imp.local', 'Superviseur', 'M.', ''],   # line 2 — invalid role
            ['Ok Person', 'ok@emp-imp.local', 'OUVRIER', 'M.', ''],       # line 3 — enum value accepted
        ]))
        self.assertEqual(resp.data['created'], 1)
        self.assertFalse(User.objects.filter(email='bad@emp-imp.local').exists())
        reasons = {s['line']: s['reason'] for s in resp.data['skipped']}
        self.assertIn(2, reasons)
        self.assertIn('rôle invalide', reasons[2].lower())

    def test_admin_role_in_file_is_rejected(self):
        resp = self._upload(self._xlsx([['X', 'x@emp-imp.local', 'ADMIN', 'M.', '']]))
        self.assertEqual(resp.data['created'], 0)
        self.assertEqual(len(resp.data['skipped']), 1)

    def test_never_deletes_an_employee_absent_from_the_file(self):
        self._upload(self._xlsx([['New Only', 'newonly@emp-imp.local', 'Fermier', 'M.', '']]))
        self.assertTrue(User.objects.filter(email='marie@emp-imp.local').exists())

    def test_role_profile_row_is_swapped_on_role_change(self):
        from apps.core.models import Farmer, Worker
        self.assertTrue(Worker.objects.filter(user=self.existing).exists())
        self._upload(self._xlsx([['Marie', 'marie@emp-imp.local', 'Fermier', 'Mme', '']]))
        self.assertFalse(Worker.objects.filter(user=self.existing).exists())
        self.assertTrue(Farmer.objects.filter(user=self.existing).exists())

    def test_farmer_cannot_import_employees(self):
        farmer = User.objects.create_user(email='f@emp-imp.local', password='x', name='F', role=UserRole.FARMER, farm=self.farm)
        create_role_profile(farmer)
        self.client.force_authenticate(user=farmer)
        resp = self._upload(self._xlsx([['X', 'z@emp-imp.local', 'Fermier', 'M.', '']]))
        self.assertEqual(resp.status_code, 403)
