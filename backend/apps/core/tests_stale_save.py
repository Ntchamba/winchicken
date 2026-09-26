"""A stale editor's save must not delete what it never saw (campaign 9, finding B13).

The app stays open all day on phones. The stock and protocol PUTs are upserts that delete every
row the client did not send — so a second tab (or a colleague's phone) that loaded the list
before an article or protocol line was added, and then saved, silently deleted that new row:
the article with its stock movements, the line with its task completions. The editors now send
the keys they loaded (`known_codes` / `known_ids`) and only those can be deleted by omission.
"""
import datetime as dt

from rest_framework.test import APITestCase

from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse
from apps.protocols.models import ProtocolCategory, ProtocolTemplate
from apps.stock.models import StockCategory, StockItem, StockMovement


class StaleSaveBase(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Onglets')
        admin = User.objects.create_user(email='admin@tabs.local', password='x', name='A', role=UserRole.ADMIN, farm=self.farm)
        create_role_profile(admin)
        self.client.force_authenticate(user=admin)


class StockStaleSaveTests(StaleSaveBase):
    def setUp(self):
        super().setUp()
        self.cat = StockCategory.objects.create(farm=self.farm, label='Aliment', kind='FEED')
        self.url = f'/api/farms/{self.farm.id}/stock-items/'
        StockItem.objects.create(item_code=f'FEE-{self.farm.id}-001', farm=self.farm, category=self.cat, name='Ancien', unit='kg')

    def rows(self):
        return self.client.get(self.url).data['items']

    def add_elsewhere(self):
        """Tab A adds an article and stocks 25 kg of it."""
        new = StockItem.objects.create(item_code=f'FEE-{self.farm.id}-002', farm=self.farm, category=self.cat, name='Nouveau', unit='kg')
        StockMovement.objects.create(item=new, movement_type='IN', quantity=25, movement_date=dt.date.today())
        return new

    def test_a_stale_save_keeps_an_article_it_never_loaded(self):
        stale = self.rows()
        self.add_elsewhere()
        known = [r['item_code'] for r in stale]
        response = self.client.put(self.url, {'items': stale, 'known_codes': known}, format='json')
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertTrue(StockItem.objects.filter(name='Nouveau').exists())
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_removing_a_loaded_article_still_deletes_it(self):
        loaded = self.rows()
        response = self.client.put(self.url, {'items': [], 'known_codes': [r['item_code'] for r in loaded]}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(StockItem.objects.exists())

    def test_without_known_codes_the_old_full_replace_rule_stands(self):
        stale = self.rows()
        self.add_elsewhere()
        self.client.put(self.url, {'items': stale}, format='json')
        self.assertFalse(StockItem.objects.filter(name='Nouveau').exists())


class ProtocolStaleSaveTests(StaleSaveBase):
    def setUp(self):
        super().setUp()
        self.house = PoultryHouse.objects.create(house_code=f'H-{self.farm.id}-001', farm=self.farm, name='A', max_capacity=10)
        self.cat = ProtocolCategory.objects.filter(house=self.house).first()
        self.url = f'/api/houses/{self.house.house_code}/protocol/'
        self.line('Ancienne')

    def line(self, what):
        return ProtocolTemplate.objects.create(house=self.house, category=self.cat, from_value=0, from_unit='DAY',
                                               until_end=True, what=what, details='')

    def test_a_stale_save_keeps_a_line_it_never_loaded(self):
        stale = self.client.get(self.url).data
        self.line('Nouvelle')
        response = self.client.put(self.url, {'lines': stale, 'known_ids': [l['id'] for l in stale]}, format='json')
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertTrue(ProtocolTemplate.objects.filter(what='Nouvelle').exists())

    def test_removing_a_loaded_line_still_deletes_it(self):
        loaded = self.client.get(self.url).data
        self.client.put(self.url, {'lines': [], 'known_ids': [l['id'] for l in loaded]}, format='json')
        self.assertFalse(ProtocolTemplate.objects.exists())
