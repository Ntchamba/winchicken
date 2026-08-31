from datetime import date

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.batches.models import BatchStatus, PoultryBatch, ProductionType
from apps.core.models import Farm, User, UserRole, create_role_profile
from apps.houses.models import PoultryHouse
from apps.stock.calculations import current_quantity, stock_evolution
from apps.stock.models import (
    MovementType, StockCategory, StockComposition, StockItem, StockMovement, Supplier,
)


def _make_user(farm, role=UserRole.ADMIN, email='admin@stock-test.local'):
    user = User.objects.create_user(email=email, password='x', name='U', role=role, farm=farm)
    create_role_profile(user)
    return user


class StockCategorySeedingTests(APITestCase):
    def test_new_farm_seeds_four_stock_categories(self):
        farm = Farm.objects.create(name='Ferme Seed')
        cats = StockCategory.objects.filter(farm=farm)
        self.assertEqual(cats.count(), 4)
        self.assertEqual(
            set(cats.values_list('kind', flat=True)),
            {'FEED', 'VETERINARY', 'EQUIPMENT', 'BEDDING'},
        )
        self.assertEqual([c.label for c in cats.order_by('sort_order')],
                         ['Aliment', 'Vétérinaire', 'Équipement', 'Litière'])


class StockCategoryApiTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Cat API')
        self.admin = _make_user(self.farm)
        self.worker = _make_user(self.farm, role=UserRole.WORKER, email='worker@stock-test.local')
        self.client.force_authenticate(user=self.admin)

    def test_add_custom_category_appends_and_is_custom_kind(self):
        resp = self.client.post(
            f'/api/farms/{self.farm.id}/stock-categories/', {'label': 'Biosécurité', 'icon': 'ShoppingCart'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['kind'], 'CUSTOM')
        self.assertEqual(resp.data['sort_order'], 4)

    def test_add_category_rejects_unknown_icon(self):
        resp = self.client.post(
            f'/api/farms/{self.farm.id}/stock-categories/', {'label': 'X', 'icon': 'NotARealIcon'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_worker_cannot_add_category(self):
        self.client.force_authenticate(user=self.worker)
        resp = self.client.post(
            f'/api/farms/{self.farm.id}/stock-categories/', {'label': 'X', 'icon': 'Package'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_category_cascades_its_items(self):
        cat = StockCategory.objects.get(farm=self.farm, kind='FEED')
        StockItem.objects.create(item_code='FEE-1-001', farm=self.farm, category=cat, name='Aliment', unit='kg')
        resp = self.client.delete(f'/api/stock-categories/{cat.id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(StockItem.objects.filter(item_code='FEE-1-001').exists())

    def test_put_items_with_custom_category_id(self):
        cat = StockCategory.objects.create(farm=self.farm, label='Divers', icon='Package', sort_order=9)
        resp = self.client.put(
            f'/api/farms/{self.farm.id}/stock-items/',
            {'items': [{'category': cat.id, 'name': 'Bidon', 'unit': 'unité', 'alert_threshold': 2}]},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertEqual(resp.data['items'][0]['category'], cat.id)
        self.assertEqual(resp.data['items'][0]['category_kind'], 'CUSTOM')
        self.assertTrue(resp.data['items'][0]['item_code'].startswith('CUS-'))


class SupplierApiTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Supplier')
        self.admin = _make_user(self.farm)
        self.client.force_authenticate(user=self.admin)

    def test_supplier_crud_and_item_link(self):
        create = self.client.post(
            f'/api/farms/{self.farm.id}/suppliers/',
            {'name': 'Provende SARL', 'contact': '+237600000000', 'email': 'contact@provende.example'}, format='json',
        )
        self.assertEqual(create.status_code, status.HTTP_201_CREATED, create.data)
        supplier_id = create.data['id']

        cat = StockCategory.objects.get(farm=self.farm, kind='FEED')
        self.client.put(
            f'/api/farms/{self.farm.id}/stock-items/',
            {'items': [{'category': cat.id, 'name': 'Aliment démarrage', 'unit': 'kg', 'supplier': supplier_id}]},
            format='json',
        )

        listing = self.client.get(f'/api/farms/{self.farm.id}/suppliers/')
        row = listing.data['results'][0] if 'results' in listing.data else listing.data[0]
        self.assertEqual(row['item_names'], ['Aliment démarrage'])

        deleted = self.client.delete(f'/api/suppliers/{supplier_id}/')
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)
        # Item survives, supplier link nulled (SET_NULL).
        item = StockItem.objects.get(name='Aliment démarrage')
        self.assertIsNone(item.supplier_id)


class StockEvolutionTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Evolution')
        self.admin = _make_user(self.farm)
        self.client.force_authenticate(user=self.admin)
        self.cat = StockCategory.objects.get(farm=self.farm, kind='FEED')
        self.item = StockItem.objects.create(
            item_code='FEE-1-001', farm=self.farm, category=self.cat, name='Aliment', unit='kg', alert_threshold=50,
        )

    def test_running_balance_by_calendar_date(self):
        StockMovement.objects.create(item=self.item, movement_type=MovementType.IN, quantity=100, movement_date=date(2026, 1, 1))
        StockMovement.objects.create(item=self.item, movement_type=MovementType.OUT, quantity=30, movement_date=date(2026, 1, 3))
        StockMovement.objects.create(item=self.item, movement_type=MovementType.IN, quantity=10, movement_date=date(2026, 1, 5))

        series = stock_evolution(self.farm)
        self.assertEqual(len(series), 1)
        entry = series[0]
        self.assertEqual(entry['alertThreshold'], 50)
        self.assertEqual(entry['points'], [
            {'date': '2026-01-01', 'quantity': 100.0},
            {'date': '2026-01-03', 'quantity': 70.0},
            {'date': '2026-01-05', 'quantity': 80.0},
        ])

    def test_endpoint_empty_points_when_no_movements(self):
        resp = self.client.get(f'/api/farms/{self.farm.id}/stock-evolution/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data[0]['points'], [])


class CoverageEndpointTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Coverage')
        self.admin = _make_user(self.farm)
        self.client.force_authenticate(user=self.admin)
        self.cat = StockCategory.objects.get(farm=self.farm, kind='FEED')
        self.item = StockItem.objects.create(
            item_code='FEE-1-001', farm=self.farm, category=self.cat, name='Aliment', unit='kg',
        )
        StockMovement.objects.create(item=self.item, movement_type=MovementType.IN, quantity=100, movement_date=date(2026, 1, 1))

    def test_insufficient_when_days_needed_exceeds_days_remaining(self):
        resp = self.client.get(
            f'/api/stock-items/{self.item.item_code}/coverage/', {'quantity_per_day': 40, 'days': 10},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['currentQuantity'], 100)
        self.assertEqual(resp.data['daysRemaining'], 2.5)
        self.assertEqual(resp.data['daysNeeded'], 10)
        self.assertFalse(resp.data['sufficient'])

    def test_sufficient_when_stock_covers_period(self):
        resp = self.client.get(
            f'/api/stock-items/{self.item.item_code}/coverage/', {'quantity_per_day': 5, 'days': 10},
        )
        self.assertTrue(resp.data['sufficient'])

    def test_dose_per_bird_coverage_scales_with_live_birds(self):
        house = PoultryHouse.objects.create(house_code='H-COV-1', farm=self.farm, name='S', max_capacity=1000)
        PoultryBatch.objects.create(
            batch_code='B-COV-1', house=house, production_type=ProductionType.BROILER,
            initial_count=200, start_date=date(2026, 1, 1), status=BatchStatus.ACTIVE,
        )
        # 100 on hand, 0.5/bird * 200 birds = 100/day → 1 day of cover, need 10 → insufficient.
        resp = self.client.get(
            f'/api/stock-items/{self.item.item_code}/coverage/', {'dose_per_bird': 0.5, 'days': 10},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['dailyRate'], 100)
        self.assertEqual(resp.data['daysRemaining'], 1.0)
        self.assertFalse(resp.data['sufficient'])


class ManualStockMovementTests(APITestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Manual')
        self.admin = _make_user(self.farm)
        self.client.force_authenticate(user=self.admin)
        self.cat = StockCategory.objects.get(farm=self.farm, kind='EQUIPMENT')
        self.item = StockItem.objects.create(
            item_code='EQU-1-001', farm=self.farm, category=self.cat, name='Abreuvoir', unit='unité',
        )

    def test_manual_in_movement_with_note_adds_stock(self):
        resp = self.client.post('/api/stock-movements/', {
            'item': self.item.item_code, 'movement_type': 'IN', 'quantity': 12,
            'movement_date': '2026-04-01', 'note': 'Don coopérative',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        mv = StockMovement.objects.get(id=resp.data['id'])
        self.assertEqual(mv.note, 'Don coopérative')
        self.assertIsNone(mv.batch_id)
        self.assertIsNone(mv.protocol_line_id)
        self.assertEqual(current_quantity(self.item), 12)

    def test_worker_cannot_create_movement(self):
        worker = _make_user(self.farm, role=UserRole.WORKER, email='worker@stock-test.local')
        self.client.force_authenticate(user=worker)
        resp = self.client.post('/api/stock-movements/', {
            'item': self.item.item_code, 'movement_type': 'IN', 'quantity': 1, 'movement_date': '2026-04-01',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_missing_quantity_creates_no_movement(self):
        """"Ajouter du stock" with no quantity must not create a StockMovement."""
        resp = self.client.post('/api/stock-movements/', {
            'item': self.item.item_code, 'movement_type': 'IN', 'movement_date': '2026-04-01',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(StockMovement.objects.filter(item=self.item).count(), 0)
        self.assertEqual(current_quantity(self.item), 0)

    def test_total_price_creates_a_matching_expense(self):
        from apps.finance.models import Expense
        from apps.stock.models import Supplier

        feed_cat = StockCategory.objects.get(farm=self.farm, kind='FEED')
        supplier = Supplier.objects.create(farm=self.farm, name='Provende SARL')
        item = StockItem.objects.create(
            item_code='FEE-PX-1', farm=self.farm, category=feed_cat, name='Aliment', unit='sac',
            unit_price=8000, supplier=supplier,
        )
        resp = self.client.post('/api/stock-movements/', {
            'item': item.item_code, 'movement_type': 'IN', 'quantity': 5,
            'movement_date': '2026-04-02', 'total_price': '41000',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(current_quantity(item), 5)

        exp = Expense.objects.get(farm=self.farm, amount=41000)
        self.assertEqual(exp.category, 'FEED')                 # FEED item → FEED expense
        self.assertEqual(str(exp.expense_date), '2026-04-02')  # the entry's date
        self.assertIsNone(exp.batch_id)                        # general farm stock
        self.assertEqual(exp.supplier, 'Provende SARL')        # item's linked supplier name

    def test_no_total_price_creates_no_expense(self):
        from apps.finance.models import Expense

        before = Expense.objects.filter(farm=self.farm).count()
        self.client.post('/api/stock-movements/', {
            'item': self.item.item_code, 'movement_type': 'IN', 'quantity': 3, 'movement_date': '2026-04-03',
        }, format='json')
        self.assertEqual(Expense.objects.filter(farm=self.farm).count(), before)  # reference price alone ≠ a transaction

    def test_equipment_item_maps_to_depreciation_expense(self):
        from apps.finance.models import Expense

        resp = self.client.post('/api/stock-movements/', {
            'item': self.item.item_code, 'movement_type': 'IN', 'quantity': 2,
            'movement_date': '2026-04-04', 'total_price': '15000',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Expense.objects.get(farm=self.farm, amount=15000).category, 'DEPRECIATION')

    def test_item_type_keyword_overrides_category_kind_for_expense(self):
        """A free-text `item_type` files the auto-purchase under the finance category it implies,
        even when the stock category kind would map elsewhere (here: a CUSTOM category)."""
        from apps.finance.models import Expense

        custom = StockCategory.objects.create(farm=self.farm, label='Divers', icon='Package', kind='CUSTOM')
        chair = StockItem.objects.create(
            item_code='CUS-1-001', farm=self.farm, category=custom, name='Chaise',
            unit='unité', item_type='Équipement / Matériel',
        )
        sponge = StockItem.objects.create(
            item_code='CUS-1-002', farm=self.farm, category=custom, name='Éponge',
            unit='unité', item_type='Objet divers',
        )
        self.client.post('/api/stock-movements/', {
            'item': chair.item_code, 'movement_type': 'IN', 'quantity': 4,
            'movement_date': '2026-04-05', 'total_price': '20000',
        }, format='json')
        self.client.post('/api/stock-movements/', {
            'item': sponge.item_code, 'movement_type': 'IN', 'quantity': 10,
            'movement_date': '2026-04-05', 'total_price': '3000',
        }, format='json')
        self.assertEqual(Expense.objects.get(farm=self.farm, amount=20000).category, 'DEPRECIATION')
        self.assertEqual(Expense.objects.get(farm=self.farm, amount=3000).category, 'MISC')


class CurrentQuantityUnitTests(TestCase):
    """apps.stock.calculations.current_quantity — pure IN-minus-OUT, no endpoint."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Qty')
        self.item = StockItem.objects.create(
            item_code='FEE-Q-001', farm=self.farm,
            category=StockCategory.objects.get(farm=self.farm, kind='FEED'),
            name='Aliment', unit='kg',
        )

    def _mv(self, kind, qty, d='2026-01-01'):
        return StockMovement.objects.create(item=self.item, movement_type=kind, quantity=qty, movement_date=d)

    def test_zero_when_no_movements(self):
        self.assertEqual(current_quantity(self.item), 0)

    def test_in_minus_out_across_several_movements(self):
        self._mv(MovementType.IN, 100)
        self._mv(MovementType.IN, 50, '2026-01-05')
        self._mv(MovementType.OUT, 30, '2026-01-06')
        self._mv(MovementType.OUT, 20, '2026-01-07')
        self.assertEqual(current_quantity(self.item), 100)  # 150 in - 50 out

    def test_can_go_negative_if_out_exceeds_in(self):
        self._mv(MovementType.IN, 10)
        self._mv(MovementType.OUT, 25, '2026-01-02')
        self.assertEqual(current_quantity(self.item), -15)


class InlineStockItemCreateTests(APITestCase):
    """POST /api/farms/{id}/stock-items/ (one item) + PATCH /api/stock-items/{code}/ — the
    inline "+ Créer '{name}' comme nouvel article de stock" flow from a protocol row (2026-08-31)."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Inline')
        self.admin = _make_user(self.farm)
        self.worker = _make_user(self.farm, role=UserRole.WORKER, email='w@inline.local')
        self.client.force_authenticate(self.admin)

    def test_create_one_item_with_category_hint_maps_to_kind(self):
        resp = self.client.post(
            f'/api/farms/{self.farm.id}/stock-items/',
            {'name': 'Provende maison', 'category_hint': 'Alimentation'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['name'], 'Provende maison')
        self.assertEqual(resp.data['category_kind'], 'FEED')
        self.assertEqual(resp.data['unit'], 'kg')          # default
        self.assertEqual(resp.data['current_quantity'], 0)  # no movements yet — expected
        self.assertTrue(resp.data['item_code'].startswith('FEE-'))

    def test_create_falls_back_to_first_category_for_unknown_hint(self):
        resp = self.client.post(
            f'/api/farms/{self.farm.id}/stock-items/',
            {'name': 'Bidon', 'category_hint': 'Catégorie inconnue', 'unit': 'L'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['unit'], 'L')
        self.assertIn(resp.data['category_kind'], {'FEED', 'VETERINARY', 'EQUIPMENT', 'BEDDING', 'CUSTOM'})

    def test_create_rejects_blank_name_and_non_privileged_role(self):
        r1 = self.client.post(f'/api/farms/{self.farm.id}/stock-items/', {'name': '  '}, format='json')
        self.assertEqual(r1.status_code, status.HTTP_400_BAD_REQUEST)
        self.client.force_authenticate(self.worker)
        r2 = self.client.post(f'/api/farms/{self.farm.id}/stock-items/', {'name': 'X'}, format='json')
        self.assertEqual(r2.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_updates_unit_only(self):
        created = self.client.post(
            f'/api/farms/{self.farm.id}/stock-items/', {'name': 'Maïs', 'category_hint': 'Alimentation'}, format='json',
        ).data
        resp = self.client.patch(f'/api/stock-items/{created["item_code"]}/', {'unit': 'sac de 50kg'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['unit'], 'sac de 50kg')
        self.assertEqual(StockItem.objects.get(item_code=created['item_code']).unit, 'sac de 50kg')


class StockCompositionApiTests(APITestCase):
    """Compositions: recipe create/list/delete (2026-08-31). Defining a recipe writes no
    StockMovement — only executing it does (StockCompositionExecuteTests)."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Compo')
        self.admin = _make_user(self.farm)
        self.worker = _make_user(self.farm, role=UserRole.WORKER, email='w@compo.local')
        self.client.force_authenticate(self.admin)
        cat = StockCategory.objects.get(farm=self.farm, kind='FEED')
        self.mais = StockItem.objects.create(item_code='FEE-1-001', farm=self.farm, category=cat, name='Maïs', unit='kg')
        self.macabo = StockItem.objects.create(item_code='FEE-1-002', farm=self.farm, category=cat, name='Macabo', unit='kg')
        self.provende = StockItem.objects.create(item_code='FEE-1-003', farm=self.farm, category=cat, name='Provende', unit='kg')

    def _payload(self):
        return {
            'name': 'Provende maison', 'output_item': self.provende.item_code,
            'ingredients': [
                {'item': self.mais.item_code, 'quantity': 1000},
                {'item': self.macabo.item_code, 'quantity': 1000},
            ],
        }

    def test_create_composition_writes_recipe_but_no_movement(self):
        resp = self.client.post(f'/api/farms/{self.farm.id}/stock-compositions/', self._payload(), format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['name'], 'Provende maison')
        self.assertEqual(len(resp.data['ingredients']), 2)
        self.assertEqual(resp.data['ingredients'][0]['item_name'], 'Maïs')
        self.assertEqual(resp.data['ingredients'][0]['unit'], 'kg')
        self.assertEqual(resp.data['output_item_name'], 'Provende')
        self.assertEqual(StockMovement.objects.count(), 0)  # recipe ≠ execution

    def test_list_and_delete(self):
        cid = self.client.post(f'/api/farms/{self.farm.id}/stock-compositions/', self._payload(), format='json').data['id']
        listing = self.client.get(f'/api/farms/{self.farm.id}/stock-compositions/')
        rows = listing.data['results'] if 'results' in listing.data else listing.data
        self.assertEqual(len(rows), 1)
        self.assertEqual(self.client.delete(f'/api/stock-compositions/{cid}/').status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(StockComposition.objects.count(), 0)

    def test_create_rejects_no_ingredients_and_non_privileged_role(self):
        bad = {'name': 'X', 'output_item': self.provende.item_code, 'ingredients': []}
        self.assertEqual(
            self.client.post(f'/api/farms/{self.farm.id}/stock-compositions/', bad, format='json').status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.client.force_authenticate(self.worker)
        self.assertEqual(
            self.client.post(f'/api/farms/{self.farm.id}/stock-compositions/', self._payload(), format='json').status_code,
            status.HTTP_403_FORBIDDEN,
        )


class StockCompositionExecuteTests(APITestCase):
    """POST /api/stock-compositions/{id}/execute/ (2026-08-31, Step 3)."""

    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Exec')
        self.admin = _make_user(self.farm)
        self.client.force_authenticate(self.admin)
        cat = StockCategory.objects.get(farm=self.farm, kind='FEED')
        self.mais = StockItem.objects.create(item_code='FEE-1-001', farm=self.farm, category=cat, name='Maïs', unit='kg')
        self.macabo = StockItem.objects.create(item_code='FEE-1-002', farm=self.farm, category=cat, name='Macabo', unit='kg')
        self.provende = StockItem.objects.create(item_code='FEE-1-003', farm=self.farm, category=cat, name='Provende', unit='kg')
        StockMovement.objects.create(item=self.mais, movement_type=MovementType.IN, quantity=1500, movement_date=date(2026, 8, 1))
        StockMovement.objects.create(item=self.macabo, movement_type=MovementType.IN, quantity=1500, movement_date=date(2026, 8, 1))
        self.comp = self.client.post(f'/api/farms/{self.farm.id}/stock-compositions/', {
            'name': 'Provende maison', 'output_item': self.provende.item_code,
            'ingredients': [
                {'item': self.mais.item_code, 'quantity': 1000},
                {'item': self.macabo.item_code, 'quantity': 1000},
            ],
        }, format='json').data
        self.url = f'/api/stock-compositions/{self.comp["id"]}/execute/'

    def test_execute_moves_stock_in_one_transaction(self):
        resp = self.client.post(self.url, {
            'ingredients': [
                {'item': self.mais.item_code, 'quantity': 1000},
                {'item': self.macabo.item_code, 'quantity': 1000},
            ],
            'outputQuantity': 2000,  # not the sum — user-entered
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data['status'], 'done')
        self.assertEqual(len(resp.data['movements']), 3)   # 2 OUT + 1 IN
        self.assertEqual(current_quantity(self.mais), 500)     # 1500 - 1000
        self.assertEqual(current_quantity(self.macabo), 500)   # 1500 - 1000
        self.assertEqual(current_quantity(self.provende), 2000)  # + entered output

        outs = StockMovement.objects.filter(movement_type=MovementType.OUT)
        self.assertEqual(outs.count(), 2)
        for m in list(outs) + [StockMovement.objects.get(movement_type=MovementType.IN, item=self.provende)]:
            self.assertIsNone(m.batch_id)
            self.assertEqual(m.movement_date, date.today())

    def test_execute_uses_edited_ingredient_quantities(self):
        resp = self.client.post(self.url, {
            'ingredients': [
                {'item': self.mais.item_code, 'quantity': 1200},   # adjusted from base 1000
                {'item': self.macabo.item_code, 'quantity': 900},
            ],
            'outputQuantity': 2100,
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(current_quantity(self.mais), 300)     # 1500 - 1200
        self.assertEqual(current_quantity(self.macabo), 600)   # 1500 - 900

    def test_insufficient_stock_is_non_blocking_and_writes_nothing(self):
        resp = self.client.post(self.url, {
            'ingredients': [
                {'item': self.mais.item_code, 'quantity': 5000},   # > 1500 on hand
                {'item': self.macabo.item_code, 'quantity': 1000},
            ],
            'outputQuantity': 2000,
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'insufficient_stock')
        self.assertEqual(resp.data['shortfalls'][0]['itemName'], 'Maïs')
        self.assertEqual(resp.data['shortfalls'][0]['needed'], 5000)
        self.assertEqual(StockMovement.objects.filter(movement_type=MovementType.OUT).count(), 0)
        self.assertEqual(current_quantity(self.mais), 1500)   # untouched

    def test_force_executes_despite_insufficient_stock(self):
        resp = self.client.post(self.url, {
            'ingredients': [{'item': self.mais.item_code, 'quantity': 5000}, {'item': self.macabo.item_code, 'quantity': 1000}],
            'outputQuantity': 2000, 'force': True,
        }, format='json')
        self.assertEqual(resp.data['status'], 'done')
        self.assertEqual(current_quantity(self.mais), -3500)   # allowed negative

    def test_bad_output_quantity_is_rejected(self):
        resp = self.client.post(self.url, {'ingredients': [], 'outputQuantity': 0}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(StockMovement.objects.filter(movement_type=MovementType.OUT).count(), 0)
