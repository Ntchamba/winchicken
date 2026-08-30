from datetime import date

from rest_framework import status
from rest_framework.test import APITestCase

from apps.batches.models import PoultryBatch, ProductionType
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse


class MaintenanceIncidentTests(APITestCase):
    """UnusualCase/EquipmentFault open-filtering + resolve actions (docs/deviations.md Part 16,
    Part D) — a resolved incident disappears from the open-only filter but the row itself (and
    its audit-log entry) is never deleted."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Incidents Test')
        self.admin = User.objects.create_user(email='admin@incident-test.local', password='x', name='Admin', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(self.admin)
        self.technician = User.objects.create_user(email='tech@incident-test.local', password='x', name='Technicien', role=UserRole.TECHNICIAN, farm=self.farm)
        create_role_profile(self.technician)
        self.house = PoultryHouse.objects.create(house_code='H-INC-1', farm=self.farm, name='Bâtiment Incidents', max_capacity=1000)
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-INC-1', house=self.house, production_type=ProductionType.BROILER,
            initial_count=500, start_date=date.today(),
        )
        self.client.force_authenticate(user=self.admin)

    def test_unusual_case_resolve_removes_from_open_filter_but_not_from_the_database(self):
        from apps.maintenance.models import UnusualCase
        case = UnusualCase.objects.create(case_code='CASE-TEST-1', batch=self.batch, case_description='Comportement anormal')

        open_before = self.client.get('/api/unusual-cases/', {'resolved': 'false'})
        self.assertEqual(len(open_before.data['results'] if 'results' in open_before.data else open_before.data), 1)

        resolve = self.client.post(f'/api/unusual-cases/{case.case_code}/resolve/')
        self.assertEqual(resolve.status_code, status.HTTP_200_OK)
        self.assertTrue(resolve.data['resolved'])

        open_after = self.client.get('/api/unusual-cases/', {'resolved': 'false'})
        results = open_after.data['results'] if 'results' in open_after.data else open_after.data
        self.assertEqual(len(results), 0)
        self.assertTrue(UnusualCase.objects.filter(case_code=case.case_code).exists())

        audit = self.client.get('/api/audit-log/')
        actions = [e['action'] for e in (audit.data['results'] if 'results' in audit.data else audit.data)]
        self.assertIn('unusual_case.resolved', actions)

    def test_equipment_fault_resolve_sets_status_and_repaired_date(self):
        from apps.maintenance.models import EquipmentFault
        fault = EquipmentFault.objects.create(fault_code='FAULT-TEST-1', house=self.house, fault_description='Ventilateur en panne')

        self.client.force_authenticate(user=self.technician)
        response = self.client.post(f'/api/equipment-faults/{fault.fault_code}/resolve/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'RESOLVED')
        self.assertIsNotNone(response.data['repaired_date'])

        open_faults = self.client.get('/api/equipment-faults/', {'status': 'OPEN'})
        results = open_faults.data['results'] if 'results' in open_faults.data else open_faults.data
        self.assertEqual(len(results), 0)


class CaseResolutionControlTests(APITestCase):
    """Feature 5 (2026-08-27, docs/deviations.md) — explicit, role-gated resolution + the new
    "Historique" filter. `resolved`/`status` default unresolved on creation (never touched by
    this task, already correct — asserted here so a future regression is caught)."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Résolution Test')
        self.admin = User.objects.create_user(email='admin@resolve-test.local', password='x', name='Admin', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(self.admin)
        self.farm_manager = User.objects.create_user(email='fm@resolve-test.local', password='x', name='Gérant', role=UserRole.FARM_MANAGER, farm=self.farm)
        create_role_profile(self.farm_manager)
        self.farmer = User.objects.create_user(email='farmer@resolve-test.local', password='x', name='Fermier', role=UserRole.FARMER, farm=self.farm)
        create_role_profile(self.farmer)
        self.house = PoultryHouse.objects.create(house_code='H-RES-1', farm=self.farm, name='Bâtiment', max_capacity=1000)
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-RES-1', house=self.house, production_type=ProductionType.BROILER,
            initial_count=500, start_date=date.today(), farmer=self.farmer,
        )

    def test_new_case_is_never_resolved_by_default(self):
        from apps.maintenance.models import UnusualCase
        case = UnusualCase.objects.create(case_code='CASE-DEFAULT-1', batch=self.batch, case_description='...', farmer=self.farmer)
        self.assertFalse(case.resolved)
        self.assertIsNone(case.resolved_at)
        self.assertIsNone(case.resolved_by)

    def test_reporting_farmer_cannot_resolve_their_own_case(self):
        from apps.maintenance.models import UnusualCase
        case = UnusualCase.objects.create(case_code='CASE-SELF-1', batch=self.batch, case_description='...', farmer=self.farmer)
        self.client.force_authenticate(user=self.farmer)
        response = self.client.post(f'/api/unusual-cases/{case.case_code}/resolve/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_farm_manager_can_resolve_and_is_recorded(self):
        from apps.maintenance.models import UnusualCase
        case = UnusualCase.objects.create(case_code='CASE-FM-1', batch=self.batch, case_description='...', farmer=self.farmer)
        self.client.force_authenticate(user=self.farm_manager)
        response = self.client.post(f'/api/unusual-cases/{case.case_code}/resolve/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['resolved_by'], self.farm_manager.id)
        self.assertEqual(response.data['resolvedByName'], 'Gérant')

    def test_resolved_case_appears_in_history_filter_with_resolver_and_timestamp(self):
        from apps.maintenance.models import UnusualCase
        case = UnusualCase.objects.create(case_code='CASE-HIST-1', batch=self.batch, case_description='Signalement test', farmer=self.farmer)
        self.client.force_authenticate(user=self.admin)
        self.client.post(f'/api/unusual-cases/{case.case_code}/resolve/')

        history = self.client.get('/api/unusual-cases/', {'resolved': 'true'})
        results = history.data['results'] if 'results' in history.data else history.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['case_code'], 'CASE-HIST-1')
        self.assertEqual(results[0]['resolvedByName'], 'Admin')
        self.assertIsNotNone(results[0]['resolved_at'])
        # Original report details stay intact in the history record.
        self.assertEqual(results[0]['case_description'], 'Signalement test')

        still_open = self.client.get('/api/unusual-cases/', {'resolved': 'false'})
        self.assertEqual(len(still_open.data['results'] if 'results' in still_open.data else still_open.data), 0)

    def test_resolved_fault_appears_in_history_filter_with_resolver(self):
        from apps.maintenance.models import EquipmentFault
        technician = User.objects.create_user(email='tech@resolve-test.local', password='x', name='Technicien', role=UserRole.TECHNICIAN, farm=self.farm)
        create_role_profile(technician)
        fault = EquipmentFault.objects.create(fault_code='FAULT-HIST-1', house=self.house, fault_description='Panne test')
        self.client.force_authenticate(user=technician)
        self.client.post(f'/api/equipment-faults/{fault.fault_code}/resolve/')

        history = self.client.get('/api/equipment-faults/', {'status': 'RESOLVED'})
        results = history.data['results'] if 'results' in history.data else history.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['resolvedByName'], 'Technicien')
