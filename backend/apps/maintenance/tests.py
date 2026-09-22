from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.batches.models import BatchStatus, PoultryBatch
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse
from apps.maintenance.models import EquipmentFault, EquipmentFaultStatus, UnusualCase


class MaintenanceRolePermissionTests(APITestCase):
    """Section 8 permission matrix: declaring a fault is Technician/Admin only, reporting a
    case is Farmer/Worker only — and each has a PATCH endpoint restricted the same way."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Test Farm')
        self.house = PoultryHouse.objects.create(house_code='H-TEST', farm=self.farm, name='House', max_capacity=100)
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-TEST', house=self.house, production_type='BROILER',
            initial_count=100, current_count=100, start_date='2026-01-01', status=BatchStatus.ACTIVE,
        )

    def _user(self, role, email):
        user = User.objects.create_user(email=email, name='T', role=role, farm=self.farm)
        create_role_profile(user)
        return user

    def _auth(self, user):
        token = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')

    def test_cashier_cannot_declare_equipment_fault(self):
        self._auth(self._user(UserRole.CASHIER, 'cashier@test.com'))
        resp = self.client.post('/api/equipment-faults/', {'house': self.house.house_code, 'fault_description': 'Broken fan'})
        self.assertEqual(resp.status_code, 403)

    def test_technician_can_declare_and_patch_equipment_fault(self):
        self._auth(self._user(UserRole.TECHNICIAN, 'tech@test.com'))
        resp = self.client.post('/api/equipment-faults/', {'house': self.house.house_code, 'fault_description': 'Broken fan'})
        self.assertEqual(resp.status_code, 201)
        fault_code = resp.data['fault_code']
        patch = self.client.patch(f'/api/equipment-faults/{fault_code}/', {'status': 'REPAIRED', 'repaired_date': '2026-01-05'})
        self.assertEqual(patch.status_code, 200)
        fault = EquipmentFault.objects.get(fault_code=fault_code)
        self.assertEqual(fault.status, EquipmentFaultStatus.REPAIRED)

    def test_repaired_status_requires_repaired_date(self):
        self._auth(self._user(UserRole.TECHNICIAN, 'tech2@test.com'))
        create = self.client.post('/api/equipment-faults/', {'house': self.house.house_code, 'fault_description': 'Broken fan'})
        fault_code = create.data['fault_code']
        resp = self.client.patch(f'/api/equipment-faults/{fault_code}/', {'status': 'REPAIRED'})
        self.assertEqual(resp.status_code, 400)

    def test_technician_cannot_report_unusual_case(self):
        self._auth(self._user(UserRole.TECHNICIAN, 'tech3@test.com'))
        resp = self.client.post('/api/unusual-cases/', {'batch': self.batch.batch_code, 'case_description': 'Sick birds'})
        self.assertEqual(resp.status_code, 403)

    def test_worker_can_report_and_edit_unusual_case(self):
        self._auth(self._user(UserRole.WORKER, 'worker@test.com'))
        resp = self.client.post('/api/unusual-cases/', {'batch': self.batch.batch_code, 'case_description': 'Sick birds'})
        self.assertEqual(resp.status_code, 201)
        case_code = resp.data['case_code']
        patch = self.client.patch(f'/api/unusual-cases/{case_code}/', {'case_description': 'Sick birds, respiratory distress'})
        self.assertEqual(patch.status_code, 200)
        case = UnusualCase.objects.get(case_code=case_code)
        self.assertEqual(case.case_description, 'Sick birds, respiratory distress')
