"""Executing a `StockComposition` (2026-08-31) — the only place a composition moves stock.

`execute_composition` runs a recipe: one `OUT` `StockMovement` per ingredient at its entered
quantity, one `IN` for the output item at the user-entered output quantity, all in one
transaction. Output quantity is never derived from the inputs — real processing loses or gains
weight/volume, so the operator types the actual amount produced.
"""
import math

from django.db import transaction
from django.utils import timezone

from apps.core.formatting import fr_number


def _positive_quantity(raw):
    """`raw` as a finite float > 0, or None. float() alone accepts "nan" and "inf", and a
    NaN or infinite StockMovement would poison every total that sums it."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def _shortfalls(composition, quantities):
    """List of ingredients whose entered quantity exceeds current on-hand stock — the
    non-blocking "stock insuffisant" warning, same shape the protocol coverage check uses."""
    from apps.stock.calculations import current_quantity

    out = []
    for ing in composition.ingredients.all():
        need = quantities.get(ing.item_id, ing.quantity)
        have = current_quantity(ing.item)
        if have < need:
            out.append({
                'itemCode': ing.item_id, 'itemName': ing.item.name, 'unit': ing.item.unit,
                'needed': need, 'onHand': have,
            })
    return out


def auto_deduct_ingredients_for_output(item, produced_quantity, movement_date):
    """Adding `produced_quantity` of `item` to stock was flagged as a production run — deduct
    the recipe ingredients as if `execute_composition` had produced that amount.

    Picks the first `StockComposition` whose `output_item` is `item` and whose
    `base_output_quantity` is set (> 0), ordered by name. Each ingredient is deducted at
    `ingredient.quantity * produced_quantity / base_output_quantity` — one `OUT` `StockMovement`
    dated `movement_date`, in the caller's transaction. Non-blocking on shortfalls (mirrors
    `execute_composition` under force + the protocol coverage check): the OUT is still written,
    the shortfall only reported back. No-op (returns `{'status': 'noop'}`) when `item` is no
    recipe's output or none has a usable base yield, or when `produced_quantity` <= 0.

    Returns `{'status': 'done', 'composition': name, 'movements': [id...], 'shortfalls': [...]}`
    or `{'status': 'noop'}`.
    """
    from apps.stock.calculations import current_quantity
    from apps.stock.models import MovementType, StockComposition, StockMovement

    produced_quantity = _positive_quantity(produced_quantity)
    if produced_quantity is None:
        return {'status': 'noop'}

    composition = (
        StockComposition.objects
        .filter(output_item=item, base_output_quantity__gt=0)
        .order_by('name', 'id')
        .prefetch_related('ingredients__item')
        .first()
    )
    if composition is None:
        return {'status': 'noop'}

    factor = produced_quantity / composition.base_output_quantity
    note = f'Décompté auto · production de {fr_number(produced_quantity, 3)} {item.unit} « {composition.name} »'
    created, shortfalls = [], []
    with transaction.atomic():
        for ing in composition.ingredients.all():
            need = ing.quantity * factor
            have = current_quantity(ing.item)
            if have < need:
                shortfalls.append({
                    'itemCode': ing.item_id, 'itemName': ing.item.name, 'unit': ing.item.unit,
                    'needed': need, 'onHand': have,
                })
            created.append(StockMovement.objects.create(
                item=ing.item, batch=None, movement_type=MovementType.OUT,
                quantity=need, movement_date=movement_date, note=note,
            ))

    return {
        'status': 'done', 'composition': composition.name,
        'movements': [m.id for m in created], 'shortfalls': shortfalls,
    }


def execute_composition(composition, ingredient_rows, output_quantity, *, force=False):
    """Run `composition`.

    `ingredient_rows` — `[{'item': item_code, 'quantity': n}, ...]` from the request; each
    ingredient defaults to its recipe base quantity if absent or non-positive. `output_quantity`
    — user-entered, required, > 0.

    Returns:
      - `{'status': 'insufficient_stock', 'shortfalls': [...], 'http_status': 200}` when a
        shortfall exists and `force` is falsy — nothing is written.
      - `{'status': 'done', 'shortfalls': [...], 'movements': [id, ...], 'http_status': 200}`
        otherwise (shortfalls still reported for the record).
      - `{'detail': ..., 'http_status': 400}` on a bad output quantity.
    """
    from apps.stock.models import MovementType, StockMovement

    parsed = _positive_quantity(output_quantity)
    if parsed is None:
        try:
            float(output_quantity)
        except (TypeError, ValueError):
            return {'detail': 'Quantité produite invalide.', 'http_status': 400}
        return {'detail': 'La quantité produite doit être un nombre positif.', 'http_status': 400}
    output_quantity = parsed

    valid_ids = {ing.item_id for ing in composition.ingredients.all()}
    quantities = {}
    for row in ingredient_rows:
        code = row.get('item')
        if code not in valid_ids:
            continue
        q = _positive_quantity(row.get('quantity'))
        if q is not None:
            quantities[code] = q

    shortfalls = _shortfalls(composition, quantities)
    if shortfalls and not force:
        return {'status': 'insufficient_stock', 'shortfalls': shortfalls, 'http_status': 200}

    today = timezone.localdate()
    created = []
    with transaction.atomic():
        for ing in composition.ingredients.select_related('item'):
            qty = quantities.get(ing.item_id, ing.quantity)
            created.append(StockMovement.objects.create(
                item=ing.item, batch=None, movement_type=MovementType.OUT,
                quantity=qty, movement_date=today,
            ))
        created.append(StockMovement.objects.create(
            item=composition.output_item, batch=None, movement_type=MovementType.IN,
            quantity=output_quantity, movement_date=today,
        ))

    return {'status': 'done', 'shortfalls': shortfalls, 'movements': [m.id for m in created], 'http_status': 200}
