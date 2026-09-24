"""Boundaries of apps.stock.compositions — the recipes that turn ingredients into feed and are the
only other way (besides a completed protocol task) that stock moves.

Pinned: the shortfall boundary (exactly enough is not short), force vs. no force, the pro-rata
auto-deduction, and the inputs that must never become a stock movement: zero, negative, words,
and the float spellings "nan" / "inf" that float() accepts.
"""
import datetime as dt
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.core.models import Farm
from apps.stock.calculations import current_quantity
from apps.stock.compositions import auto_deduct_ingredients_for_output, execute_composition
from apps.stock.models import (
    MovementType, StockCategory, StockComposition, StockCompositionIngredient, StockItem, StockMovement,
)

TODAY = dt.date(2026, 9, 24)


class CompositionBase(TestCase):
    def setUp(self):
        self.farm = Farm.objects.create(name='Ferme Recettes')
        self.feed = StockCategory.objects.get(farm=self.farm, kind='FEED')
        self._seq = 0
        self.maize = self.item('Maïs', stock=100)
        self.soy = self.item('Soja', stock=40)
        self.mash = self.item('Aliment croissance', stock=0)
        self.recipe = StockComposition.objects.create(farm=self.farm, name='Croissance', output_item=self.mash, base_output_quantity=100)
        StockCompositionIngredient.objects.create(composition=self.recipe, item=self.maize, quantity=60)
        StockCompositionIngredient.objects.create(composition=self.recipe, item=self.soy, quantity=40)

    def item(self, name, stock):
        self._seq += 1
        item = StockItem.objects.create(
            item_code=f'REC-{self.farm.id}-{self._seq}', farm=self.farm, category=self.feed, name=name,
            unit='kg', alert_threshold=0, unit_price=Decimal('1'),
        )
        if stock:
            StockMovement.objects.create(item=item, movement_type=MovementType.IN, quantity=stock, movement_date=TODAY)
        return item

    def movements(self):
        return StockMovement.objects.exclude(movement_type=MovementType.IN, quantity__in=[100, 40])


class ExecuteCompositionTests(CompositionBase):
    def run_it(self, rows=(), output=100, force=False):
        with patch('django.utils.timezone.localdate', return_value=TODAY):
            return execute_composition(self.recipe, list(rows), output, force=force)

    def test_exactly_the_stock_on_hand_is_not_a_shortfall(self):
        result = self.run_it(output=100)      # needs 60 maize (100 on hand), 40 soy (40 on hand)
        self.assertEqual(result['status'], 'done')
        self.assertEqual(result['shortfalls'], [])
        self.assertEqual(current_quantity(self.soy), 0)
        self.assertEqual(current_quantity(self.maize), 40)
        self.assertEqual(current_quantity(self.mash), 100)

    def test_one_unit_short_stops_without_force_and_writes_nothing(self):
        before = StockMovement.objects.count()
        result = self.run_it(rows=[{'item': self.soy.item_code, 'quantity': 41}])
        self.assertEqual(result['status'], 'insufficient_stock')
        self.assertEqual([s['itemCode'] for s in result['shortfalls']], [self.soy.item_code])
        self.assertEqual(result['shortfalls'][0]['needed'], 41)
        self.assertEqual(StockMovement.objects.count(), before)

    def test_force_writes_anyway_and_still_reports_the_shortfall(self):
        result = self.run_it(rows=[{'item': self.soy.item_code, 'quantity': 41}], force=True)
        self.assertEqual(result['status'], 'done')
        self.assertEqual(len(result['shortfalls']), 1)
        self.assertEqual(current_quantity(self.soy), -1)

    def test_entered_quantities_override_the_recipe_and_bad_rows_fall_back_to_it(self):
        self.run_it(rows=[
            {'item': self.maize.item_code, 'quantity': '55,5'},   # not a number -> recipe 60
            {'item': self.soy.item_code, 'quantity': 30},
            {'item': 'INCONNU', 'quantity': 999},                  # not an ingredient -> ignored
        ], output=90)
        self.assertEqual(current_quantity(self.maize), 40)
        self.assertEqual(current_quantity(self.soy), 10)
        self.assertEqual(current_quantity(self.mash), 90)

    def test_zero_or_negative_ingredient_quantities_fall_back_to_the_recipe(self):
        self.run_it(rows=[{'item': self.maize.item_code, 'quantity': 0}, {'item': self.soy.item_code, 'quantity': -5}])
        self.assertEqual(current_quantity(self.maize), 40)
        self.assertEqual(current_quantity(self.soy), 0)

    def test_the_output_quantity_must_be_a_positive_number(self):
        before = StockMovement.objects.count()
        for bad in (0, -1, 'beaucoup', None):
            result = self.run_it(output=bad)
            self.assertEqual(result['http_status'], 400, bad)
        self.assertEqual(StockMovement.objects.count(), before)

    def test_nan_and_infinity_never_become_stock(self):
        # float() accepts these spellings; a NaN or infinite movement would poison every stock
        # total that sums it.
        before = StockMovement.objects.count()
        for bad in ('nan', 'inf', '-inf', float('nan'), float('inf')):
            result = self.run_it(output=bad)
            self.assertEqual(result.get('http_status'), 400, bad)
        self.run_it(rows=[{'item': self.soy.item_code, 'quantity': 'inf'}], force=True)
        quantities = list(StockMovement.objects.values_list('quantity', flat=True))
        self.assertTrue(all(q == q and q not in (float('inf'), float('-inf')) for q in quantities), quantities)
        self.assertEqual(current_quantity(self.soy), 0)   # fell back to the recipe's 40
        self.assertEqual(StockMovement.objects.count(), before + 3)


class AutoDeductTests(CompositionBase):
    def test_deducts_each_ingredient_pro_rata_to_the_amount_produced(self):
        result = auto_deduct_ingredients_for_output(self.mash, 50, TODAY)
        self.assertEqual(result['status'], 'done')
        self.assertEqual(current_quantity(self.maize), 70)   # 60 * 50/100
        self.assertEqual(current_quantity(self.soy), 20)     # 40 * 50/100

    def test_exactly_enough_is_not_a_shortfall(self):
        result = auto_deduct_ingredients_for_output(self.mash, 100, TODAY)   # needs 40 soy, has 40
        self.assertEqual(result['shortfalls'], [])
        self.assertEqual(current_quantity(self.soy), 0)

    def test_a_shortfall_is_reported_but_the_deduction_still_happens(self):
        result = auto_deduct_ingredients_for_output(self.mash, 150, TODAY)   # needs 60 soy, has 40
        self.assertEqual([s['itemCode'] for s in result['shortfalls']], [self.soy.item_code])
        self.assertEqual(current_quantity(self.soy), -20)

    def test_noop_cases(self):
        for produced in (0, -3, 'x', None, 'nan', 'inf'):
            self.assertEqual(auto_deduct_ingredients_for_output(self.mash, produced, TODAY), {'status': 'noop'}, produced)
        self.assertEqual(auto_deduct_ingredients_for_output(self.maize, 10, TODAY), {'status': 'noop'})
        StockComposition.objects.filter(pk=self.recipe.pk).update(base_output_quantity=0)
        self.assertEqual(auto_deduct_ingredients_for_output(self.mash, 10, TODAY), {'status': 'noop'})

    def test_the_first_recipe_by_name_wins(self):
        other = StockComposition.objects.create(farm=self.farm, name='Autre', output_item=self.mash, base_output_quantity=10)
        StockCompositionIngredient.objects.create(composition=other, item=self.soy, quantity=1)
        self.assertEqual(auto_deduct_ingredients_for_output(self.mash, 10, TODAY)['composition'], 'Autre')

    def test_the_movement_note_is_french(self):
        auto_deduct_ingredients_for_output(self.mash, 2.5, TODAY)
        note = StockMovement.objects.filter(item=self.maize, movement_type=MovementType.OUT).get().note
        self.assertEqual(note, 'Décompté auto · production de 2,5 kg « Croissance »')
