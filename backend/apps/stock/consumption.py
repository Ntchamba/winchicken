"""Validation-triggered stock deduction — the *only* protocol-driven deduction mechanism as of
2026-08-31 (the automatic daily Celery task was removed). A `ProtocolTemplate` occurrence is
consumed when a user marks it done ("Marquer comme fait"); if the row links a `stock_item` and
a quantity, that produces one `OUT` `StockMovement`. Idempotent via `TaskCompletion`.
"""
from django.db import transaction
from django.utils import timezone


def needed_quantity(line, batch):
    """The amount one validated occurrence of `line` consumes: `quantity_per_day` (fixed) or
    `dose_per_bird * batch.current_count`, or `None` if the row declares no quantity."""
    if line.quantity_per_day is not None:
        return line.quantity_per_day
    if line.dose_per_bird is not None:
        return line.dose_per_bird * batch.current_count
    return None


def stock_shortfall(line, batch):
    """`(needed, on_hand)` when the linked item's current quantity is below what this occurrence
    needs, else `None`. Used for the validation-time warning (non-blocking)."""
    from apps.stock.calculations import current_quantity

    if line.stock_item_id is None:
        return None
    needed = needed_quantity(line, batch)
    if not needed or needed <= 0:
        return None
    on_hand = current_quantity(line.stock_item)
    return (needed, on_hand) if on_hand < needed else None


def complete_task_occurrence(line, batch, *, when=None, time_slot=None, user=None, force=False):
    """Validate one occurrence of `line` for `batch`.

    Returns a dict:
      - `{'needs_confirmation': True, 'shortfall': {...}}` if stock is insufficient and `force`
        is falsy — nothing is written; the caller shows the warning and re-submits with force.
      - otherwise `{'completion': <TaskCompletion>, 'movement': <StockMovement|None>,
        'already_done': bool}`.

    Idempotent: a second call for the same `(line, batch, date, time_slot)` returns the existing
    `TaskCompletion` and creates no second `StockMovement`.
    """
    from apps.protocols.models import TaskCompletion
    from apps.stock.models import MovementType, StockMovement

    now = when or timezone.now()
    day = now.date()

    shortfall = stock_shortfall(line, batch)
    if shortfall and not force:
        needed, on_hand = shortfall
        return {'needs_confirmation': True, 'shortfall': {
            'itemCode': line.stock_item.item_code, 'itemName': line.stock_item.name,
            'unit': line.stock_item.unit, 'needed': needed, 'onHand': on_hand,
        }}

    with transaction.atomic():
        completion, created = TaskCompletion.objects.select_for_update().get_or_create(
            protocol_template=line, batch=batch, date=day, time_slot=time_slot,
            defaults={'completed_by': user},
        )
        if not created:
            return {'completion': completion, 'movement': completion.stock_movement, 'already_done': True}

        movement = None
        needed = needed_quantity(line, batch)
        if line.stock_item_id is not None and needed and needed > 0:
            movement = StockMovement.objects.create(
                item=line.stock_item, batch=batch, protocol_line=line,
                movement_type=MovementType.OUT, quantity=needed, movement_date=day,
            )
            completion.stock_movement = movement
            completion.save(update_fields=['stock_movement'])

    return {'completion': completion, 'movement': movement, 'already_done': False}


def uncomplete_task_occurrence(line, batch, *, when=None, time_slot=None):
    """Undo one validated occurrence — for the worker who tapped the wrong row.

    Deletes the `TaskCompletion` and the `OUT` `StockMovement` it created, which puts the
    quantity back (`current_quantity` is `sum(IN) - sum(OUT)`, computed at read time). The
    movement is deleted rather than offset with a compensating `IN`: this retracts an entry
    that should never have existed, and a mis-tap followed by an undo should not leave two
    rows in the article's movement history for every correction.

    Returns `{'undone': bool, 'restored': <quantity or None>}`. Undoing something that was
    never completed is a no-op, not an error — the two clients can race on a double-tap.
    """
    from apps.protocols.models import TaskCompletion

    now = when or timezone.now()
    day = now.date()

    with transaction.atomic():
        # No select_related on `stock_movement` here: it is a nullable FK, so it joins as a
        # LEFT OUTER JOIN and Postgres refuses FOR UPDATE across one. The movement is fetched
        # on access instead — one extra query on an action that happens once per undo.
        completion = TaskCompletion.objects.select_for_update().filter(
            protocol_template=line, batch=batch, date=day, time_slot=time_slot,
        ).first()
        if completion is None:
            return {'undone': False, 'restored': None}

        movement = completion.stock_movement
        restored = movement.quantity if movement else None
        completion.delete()
        if movement is not None:
            movement.delete()

    return {'undone': True, 'restored': restored}
