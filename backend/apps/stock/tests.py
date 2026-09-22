from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.batches.models import BatchStatus, PoultryBatch
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse
from apps.stock.models import StockItem


class VaccinationRolePermissionTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Test Farm')
        self.house = PoultryHouse.objects.create(house_code='H-TEST', farm=self.farm, name='House', max_capacity=100)
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-TEST', house=self.house, production_type='BROILER',
            initial_count=100, current_count=100, start_date='2026-01-01', status=BatchStatus.ACTIVE,
        )
        self.item = StockItem.objects.create(item_code='VET-1-001', farm=self.farm, category='VETERINARY', name='Vaccine', unit='dose')

    def _auth_as(self, role):
        user = User.objects.create_user(email=f'{role.lower()}@test.com', name='T', role=role, farm=self.farm)
        create_role_profile(user)
        token = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')

    def test_cashier_cannot_record_vaccination(self):
        self._auth_as(UserRole.CASHIER)
        resp = self.client.post('/api/vaccinations/', {
            'batch': self.batch.batch_code, 'item': self.item.item_code,
            'scheduled_date': '2026-01-10', 'doses_used': 100,
        })
        self.assertEqual(resp.status_code, 403)

    def test_technician_can_record_vaccination(self):
        self._auth_as(UserRole.TECHNICIAN)
        resp = self.client.post('/api/vaccinations/', {
            'batch': self.batch.batch_code, 'item': self.item.item_code,
            'scheduled_date': '2026-01-10', 'doses_used': 100,
        })
        self.assertEqual(resp.status_code, 201)
