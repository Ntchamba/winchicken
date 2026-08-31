"""Executing a `StockComposition` (2026-08-31) — the only place a composition moves stock.

`execute_composition` runs a recipe: one `OUT` `StockMovement` per ingredient at its entered
quantity, one `IN` for the output item at the user-entered output quantity, all in one
transaction. Output quantity is never derived from the inputs — real processing loses or gains
weight/volume, so the operator types the actual amount produced.
"""
from django.db import transaction
from django.utils import timezone


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

    try:
        output_quantity = float(output_quantity)
    except (TypeError, ValueError):
        return {'detail': 'Quantité produite invalide.', 'http_status': 400}
    if output_quantity <= 0:
        return {'detail': 'La quantité produite doit être positive.', 'http_status': 400}

    valid_ids = {ing.item_id for ing in composition.ingredients.all()}
    quantities = {}
    for row in ingredient_rows:
        code = row.get('item')
        if code not in valid_ids:
            continue
        try:
            q = float(row.get('quantity'))
        except (TypeError, ValueError):
            continue
        if q > 0:
            quantities[code] = q

    shortfalls = _shortfalls(composition, quantities)
    if shortfalls and not force:
        return {'status': 'insufficient_stock', 'shortfalls': shortfalls, 'http_status': 200}

    today = timezone.now().date()
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
