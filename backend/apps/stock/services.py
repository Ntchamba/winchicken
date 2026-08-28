"""Stock business logic kept out of views.py (see docs/architecture.md).

`run_daily_consumption` is the automatic daily stock deduction driven by the protocol
(2026-08-28): every ACTIVE batch's house protocol rows that declare `stock_item` +
`quantity_per_day` and whose day range covers today produce one `OUT` StockMovement per batch
per row per calendar date. Idempotent — safe to re-run the same day.
"""
from django.db import transaction
from django.utils import timezone


def run_daily_consumption(today=None):
    """Create the day's automatic consumption `StockMovement` rows and return them.

    For each `ACTIVE` `PoultryBatch`, compute its day-of-cycle, then for every
    `ProtocolTemplate` row of its house that has both `stock_item` and `quantity_per_day` set
    and whose range covers today (`apps.houses.services._protocol_line_occurrence`), create an
    `OUT` movement of `quantity_per_day` dated today — **unless** one already exists for that
    exact `(item, batch, protocol_line, movement_date)` combination (idempotency). The existing
    `on_stock_movement_saved` signal then runs the LOW_STOCK check for each affected item, so no
    alert wiring is needed here.
    """
    from apps.batches.models import BatchStatus, PoultryBatch
    from apps.houses.services import _protocol_line_occurrence
    from apps.protocols.models import ProtocolTemplate
    from apps.stock.models import MovementType, StockMovement

    today = today or timezone.now().date()
    created = []

    with transaction.atomic():
        batches = PoultryBatch.objects.filter(status=BatchStatus.ACTIVE).select_related('house')
        for batch in batches:
            day_of_cycle = (today - batch.start_date).days
            lines = ProtocolTemplate.objects.filter(
                house=batch.house, stock_item__isnull=False, quantity_per_day__isnull=False,
            ).select_related('stock_item')
            for line in lines:
                if _protocol_line_occurrence(line, day_of_cycle) is None:
                    continue
                exists = StockMovement.objects.filter(
                    item=line.stock_item, batch=batch, protocol_line=line,
                    movement_date=today, movement_type=MovementType.OUT,
                ).exists()
                if exists:
                    continue
                created.append(StockMovement.objects.create(
                    item=line.stock_item,
                    batch=batch,
                    protocol_line=line,
                    movement_type=MovementType.OUT,
                    quantity=line.quantity_per_day,
                    movement_date=today,
                ))

    return created
