"""Saving stock parameters must not destroy everything that points at a StockItem.

`PUT /api/farms/{id}/stock-items/` used to delete every row and recreate it. Five models
CASCADE off StockItem (StockMovement, PurchaseOrder, Vaccination, and both halves of
StockComposition) and two more are SET_NULL (EquipmentFault.item, ProtocolTemplate.stock_item),
so an ordinary save wiped the lot. The severed `ProtocolTemplate.stock_item` is the one that
bites hardest: it stops protocol-driven deduction dead and nothing says so.

Re-sending the same `item_code` did not save it either — the `delete()` nulls the FK first, and
recreating a row with the same primary key does not bring the FK back.

These send the GET payload straight back, unchanged, exactly the way the form does when a user
opens "Mettre à jour le stock" and presses save without touching anything (FIX 3.5, bug B).
"""
import datetime as dt
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.batches.models import BatchStatus, PoultryBatch, ProductionType
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.finance.models import PurchaseOrder
from apps.houses.models import PoultryHouse
from apps.protocols.models import ProtocolCategory, ProtocolTemplate
from apps.stock.calculations import current_quantity
from apps.stock.models import (
    MovementType, StockCategory, StockComposition, StockCompositionIngredient, StockItem,
    StockMovement, Vaccination,
)


class StockParametersUpsertTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Upsert')
        self.admin = User.objects.create_user(
            email='admin@upsert.local', password='x', name='Admin',
            role=UserRole.ADMIN, farm=self.farm,
        )
        create_role_profile(self.admin)
        self.house = PoultryHouse.objects.create(
            house_code=f'H-{self.farm.id}-001', farm=self.farm, name='Poulailler', max_capacity=500,
        )
        self.batch = PoultryBatch.objects.create(
            batch_code='BATCH-U-1', house=self.house, name='Bande', production_type=ProductionType.BROILER,
            initial_count=500, start_date=dt.date.today() - dt.timedelta(days=1),
            planned_end_date=dt.date.today() + dt.timedelta(days=55), status=BatchStatus.ACTIVE,
        )

        feed = StockCategory.objects.get(farm=self.farm, kind='FEED')
        vet = StockCategory.objects.get(farm=self.farm, kind='VETERINARY')
        self.feed_item = StockItem.objects.create(
            item_code=f'FEE-{self.farm.id}-001', farm=self.farm, category=feed, name='Provende',
            unit='kg', alert_threshold=10, unit_price=Decimal('450.00'),
        )
        self.vet_item = StockItem.objects.create(
            item_code=f'VET-{self.farm.id}-001', farm=self.farm, category=vet, name='Vaccin',
            unit='dose', alert_threshold=1, unit_price=Decimal('1200.00'),
        )
        StockMovement.objects.create(
            item=self.feed_item, movement_type=MovementType.IN, quantity=500,
            movement_date=dt.date.today(),
        )
        self.order = PurchaseOrder.objects.create(
            order_code='PO-U-1', farm=self.farm, item=self.feed_item, quantity=100,
            amount=Decimal('45000.00'),
        )
        self.vaccination = Vaccination.objects.create(
            batch=self.batch, item=self.vet_item, doses_used=500,
            administered_date=dt.date.today(),
        )
        self.composition = StockComposition.objects.create(
            farm=self.farm, name='Provende maison', output_item=self.feed_item, base_output_quantity=100,
        )
        StockCompositionIngredient.objects.create(
            composition=self.composition, item=self.vet_item, quantity=1,
        )

        category = ProtocolCategory.objects.filter(house=self.house, label='Alimentation').first()
        self.line = ProtocolTemplate.objects.create(
            house=self.house, category=category, from_value=1, until_end=True,
            what='Aliment démarrage', details='', stock_item=self.feed_item, quantity_per_day=40,
        )

    def _save_unchanged(self):
        """GET the parameters and PUT them straight back — the do-nothing save."""
        self.client.force_authenticate(user=self.admin)
        read = self.client.get(f'/api/farms/{self.farm.id}/stock-items/')
        self.assertEqual(read.status_code, 200)
        items = [
            {
                'item_code': i['item_code'],
                'category': i['category'],
                'name': i['name'],
                'unit': i['unit'],
                'item_type': i['item_type'],
                'feed_stage': i['feed_stage'],
                'cold_chain_required': i['cold_chain_required'],
                'alert_threshold': i['alert_threshold'],
                'unit_price': i['unit_price'],
                'supplier': i['supplier'],
            }
            for i in read.data['items']
        ]
        written = self.client.put(
            f'/api/farms/{self.farm.id}/stock-items/', {'items': items}, format='json',
        )
        self.assertEqual(written.status_code, 200)
        return written

    def test_an_unchanged_save_keeps_every_protocol_line_linked_to_its_item(self):
        self._save_unchanged()
        self.line.refresh_from_db()
        self.assertEqual(
            self.line.stock_item_id, self.feed_item.item_code,
            'saving stock parameters must not sever the protocol line\'s resource link',
        )

    def test_an_unchanged_save_keeps_the_stock_history_and_the_level(self):
        self.assertEqual(current_quantity(self.feed_item), 500)
        self._save_unchanged()
        self.assertEqual(StockMovement.objects.filter(item=self.feed_item).count(), 1)
        self.assertEqual(current_quantity(self.feed_item), 500)

    def test_an_unchanged_save_keeps_purchase_orders_vaccinations_and_compositions(self):
        self._save_unchanged()
        self.assertTrue(PurchaseOrder.objects.filter(pk=self.order.pk).exists())
        self.assertTrue(Vaccination.objects.filter(pk=self.vaccination.pk).exists())
        self.assertTrue(StockComposition.objects.filter(pk=self.composition.pk).exists())
        self.assertEqual(self.composition.ingredients.count(), 1)

    def test_the_rows_are_updated_in_place_rather_than_recreated(self):
        self.client.force_authenticate(user=self.admin)
        read = self.client.get(f'/api/farms/{self.farm.id}/stock-items/')
        items = [
            {
                'item_code': i['item_code'], 'category': i['category'], 'name': i['name'],
                'unit': i['unit'], 'alert_threshold': i['alert_threshold'],
                'unit_price': i['unit_price'], 'supplier': i['supplier'],
            }
            for i in read.data['items']
        ]
        for entry in items:
            if entry['item_code'] == self.feed_item.item_code:
                entry['name'] = 'Provende démarrage'
                entry['alert_threshold'] = 25
        self.client.put(f'/api/farms/{self.farm.id}/stock-items/', {'items': items}, format='json')

        self.feed_item.refresh_from_db()
        self.assertEqual(self.feed_item.name, 'Provende démarrage')
        self.assertEqual(self.feed_item.alert_threshold, 25)
        # Edited in place, so what pointed at it still does.
        self.line.refresh_from_db()
        self.assertEqual(self.line.stock_item_id, self.feed_item.item_code)
        self.assertEqual(StockMovement.objects.filter(item=self.feed_item).count(), 1)

    def test_a_new_article_is_created_without_disturbing_the_others(self):
        self.client.force_authenticate(user=self.admin)
        read = self.client.get(f'/api/farms/{self.farm.id}/stock-items/')
        items = [
            {
                'item_code': i['item_code'], 'category': i['category'], 'name': i['name'],
                'unit': i['unit'], 'alert_threshold': i['alert_threshold'],
                'unit_price': i['unit_price'], 'supplier': i['supplier'],
            }
            for i in read.data['items']
        ]
        feed = StockCategory.objects.get(farm=self.farm, kind='FEED')
        items.append({'category': feed.id, 'name': 'Maïs', 'unit': 'kg', 'alert_threshold': 0,
                      'unit_price': 0, 'supplier': None})
        response = self.client.put(
            f'/api/farms/{self.farm.id}/stock-items/', {'items': items}, format='json',
        )
        self.assertEqual(response.status_code, 200)

        self.assertEqual(StockItem.objects.filter(farm=self.farm).count(), 3)
        new_item = StockItem.objects.get(farm=self.farm, name='Maïs')
        # The generated code must not collide with a kept one.
        self.assertNotIn(new_item.item_code, {self.feed_item.item_code, self.vet_item.item_code})
        self.line.refresh_from_db()
        self.assertEqual(self.line.stock_item_id, self.feed_item.item_code)

    def test_only_an_omitted_article_is_deleted(self):
        self.client.force_authenticate(user=self.admin)
        read = self.client.get(f'/api/farms/{self.farm.id}/stock-items/')
        items = [
            {
                'item_code': i['item_code'], 'category': i['category'], 'name': i['name'],
                'unit': i['unit'], 'alert_threshold': i['alert_threshold'],
                'unit_price': i['unit_price'], 'supplier': i['supplier'],
            }
            for i in read.data['items'] if i['item_code'] != self.vet_item.item_code
        ]
        self.client.put(f'/api/farms/{self.farm.id}/stock-items/', {'items': items}, format='json')

        self.assertFalse(StockItem.objects.filter(pk=self.vet_item.pk).exists())
        self.assertTrue(StockItem.objects.filter(pk=self.feed_item.pk).exists())
        self.line.refresh_from_db()
        self.assertEqual(self.line.stock_item_id, self.feed_item.item_code)
