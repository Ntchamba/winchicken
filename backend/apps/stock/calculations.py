"""Stock calculations — implementation-detail spec section 5.2, plus the 2026-08-28 stock
restructure (evolution series + protocol-driven consumption coverage)."""
from django.db.models import FloatField, Q, Sum
from django.db.models.functions import Coalesce

from apps.stock.models import MovementType


def _on_hand():
    """`SUM(IN) - SUM(OUT)` over an item's movements, as one SQL expression — the single
    definition both `current_quantity` and `with_current_quantity` evaluate."""
    moved = lambda kind: Coalesce(  # noqa: E731
        Sum('movements__quantity', filter=Q(movements__movement_type=kind)), 0.0, output_field=FloatField(),
    )
    return moved(MovementType.IN) - moved(MovementType.OUT)


def with_current_quantity(items):
    """`items` (a StockItem queryset) with each row's on-hand quantity computed in the same
    query, so a list of N articles costs one query instead of 2N. `current_quantity` reads it
    back. Only for read paths: the value is a snapshot, and a caller that writes a movement and
    then asks again needs a fresh read (a plain, un-annotated item)."""
    # Django drops Meta.ordering from an aggregating query — keep the order the list had.
    ordering = items.query.order_by or items.model._meta.ordering
    return items.annotate(on_hand_quantity=_on_hand()).order_by(*ordering)


def current_quantity(item):
    """On-hand quantity for a StockItem: `SUM(StockMovement.quantity WHERE type=IN) -
    SUM(StockMovement.quantity WHERE type=OUT)` (implementation-detail spec 5.2). Computed at
    read time by aggregation — not cached/denormalized on StockItem, so it is always consistent.
    An item loaded through `with_current_quantity` already carries the figure; any other item
    costs one aggregate query."""
    annotated = getattr(item, 'on_hand_quantity', None)
    if annotated is not None:
        return annotated
    return type(item).objects.filter(pk=item.pk).aggregate(on_hand=_on_hand())['on_hand']


def is_low(quantity, threshold):
    """The one definition of a low article: at or under its own alert threshold. The sidebar
    badge, the stock screen, the overview tree and the LOW_STOCK alert all ask this — the alert
    used to wait for strictly below, so an article sitting at its threshold showed red with a
    badge and no alert behind it."""
    return quantity <= (threshold or 0)


def stock_evolution(farm):
    """Per-item running-balance series for the stock evolution charts (2026-08-28). One entry
    per StockItem: `{itemCode, name, unit, alertThreshold, points: [{date, quantity}]}` where
    `points` is the cumulative IN-minus-OUT balance after each distinct movement date, ordered
    by calendar date (not day-of-cycle — stock isn't batch-scoped the way growth curves are).
    Items with no movements get an empty `points` list."""
    series = []
    items = farm.stock_items.select_related('category').prefetch_related('movements').order_by('category__sort_order', 'name')
    for item in items:
        running = 0.0
        by_date = {}
        for mv in sorted(item.movements.all(), key=lambda m: (m.movement_date, m.id)):
            delta = mv.quantity if mv.movement_type == MovementType.IN else -mv.quantity
            running += delta
            by_date[mv.movement_date.isoformat()] = running
        series.append({
            'itemCode': item.item_code,
            'name': item.name,
            'unit': item.unit,
            'alertThreshold': item.alert_threshold,
            'points': [{'date': d, 'quantity': q} for d, q in sorted(by_date.items())],
        })
    return series


def coverage_for(item, quantity_per_day, days, dose_per_bird=None):
    """Planning figure for the protocol form's inline "stock insuffisant" warning (2026-08-28,
    dose mode added 2026-08-30).

    `dailyRate` = the row being edited **plus** the sum of `quantity_per_day` over every *other*
    `ProtocolTemplate` row across the farm already linked to this same item (a forward-looking
    "at this rate" figure — it does not check whether each of those rows' day ranges overlaps,
    deliberately: the warning is a heads-up, not a scheduler). The row being edited contributes
    `quantity_per_day` directly in "Quantité fixe / jour" mode, or `dose_per_bird` times the
    farm's current live-bird count (summed over ACTIVE batches) in "Dose par bande" mode.
    `daysNeeded` is the row's own day-range span. Non-blocking — the caller shows a warning when
    `sufficient` is False, it never rejects a save."""
    from apps.batches.models import BatchStatus, PoultryBatch
    from apps.protocols.models import ProtocolTemplate

    other = ProtocolTemplate.objects.filter(
        house__farm=item.farm, stock_item=item, quantity_per_day__isnull=False,
    ).aggregate(total=Sum('quantity_per_day'))['total'] or 0
    if dose_per_bird is not None:
        # current_count is a computed @property (not a column) — sum it in Python.
        birds = sum(
            b.current_count
            for b in PoultryBatch.objects.filter(house__farm=item.farm, status=BatchStatus.ACTIVE)
        )
        own_rate = float(dose_per_bird) * float(birds)
    else:
        own_rate = float(quantity_per_day or 0)
    daily_rate = own_rate + float(other)
    on_hand = current_quantity(item)
    days_remaining = (on_hand / daily_rate) if daily_rate > 0 else None
    sufficient = days_remaining is None or days_remaining >= days
    return {
        'currentQuantity': on_hand,
        'dailyRate': daily_rate,
        'daysRemaining': None if days_remaining is None else round(days_remaining, 1),
        'daysNeeded': days,
        'sufficient': sufficient,
    }
