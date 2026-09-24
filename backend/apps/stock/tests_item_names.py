"""One stock article per name within a farm.

Campaign 3, in the browser: after a page reload the onboarding protocol form no longer knew the
farm's stock items, offered "Créer « Provende »" for an article that already existed, and the
API created FEE-1-002 "Provende" next to FEE-1-001. The Excel import matches articles by name,
so a duplicate name makes it update one of them at random.
"""
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.stock.models import StockCategory, StockItem


class StockItemNameTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Noms')
        admin = User.objects.create_user(email='a@noms.local', password='x', name='A', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(admin)
        self.client.force_authenticate(user=admin)
        self.feed = StockCategory.objects.get(farm=self.farm, kind='FEED')
        self.provende = StockItem.objects.create(
            item_code=f'FEE-{self.farm.id}-001', farm=self.farm, category=self.feed, name='Provende', unit='kg', unit_price=Decimal('450'),
        )
        self.url = f'/api/farms/{self.farm.id}/stock-items/'

    def row(self, item, **over):
        return {'item_code': item.item_code, 'category': item.category_id, 'name': item.name, 'unit': item.unit, **over}

    def test_inline_create_of_an_existing_name_returns_that_article(self):
        response = self.client.post(self.url, {'name': '  provende ', 'unit': 'kg'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['item_code'], self.provende.item_code)
        self.assertEqual(StockItem.objects.filter(farm=self.farm).count(), 1)

    def test_inline_create_of_a_new_name_still_creates_it(self):
        response = self.client.post(self.url, {'name': 'Maïs', 'unit': 'kg'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(StockItem.objects.filter(farm=self.farm).count(), 2)

    def test_saving_two_rows_with_the_same_name_is_refused(self):
        response = self.client.put(self.url, {'items': [
            self.row(self.provende), {'category': self.feed.id, 'name': 'PROVENDE', 'unit': 'kg'},
        ]}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('« PROVENDE »', response.data['detail'])
        self.assertEqual(StockItem.objects.filter(farm=self.farm).count(), 1)

    def test_renaming_rows_so_names_swap_is_allowed(self):
        mais = StockItem.objects.create(item_code=f'FEE-{self.farm.id}-002', farm=self.farm, category=self.feed, name='Maïs', unit='kg')
        response = self.client.put(self.url, {'items': [
            self.row(self.provende, name='Maïs'), self.row(mais, name='Provende'),
        ]}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
