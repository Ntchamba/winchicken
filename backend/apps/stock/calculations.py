"""Stock calculations — implementation-detail spec section 5.2."""
from django.db.models import Sum

from apps.stock.models import MovementType


def current_quantity(item):
    """On-hand quantity for a StockItem: `SUM(StockMovement.quantity WHERE type=IN) -
    SUM(StockMovement.quantity WHERE type=OUT)` (implementation-detail spec 5.2). Computed at
    read time by aggregation on every call — not cached/denormalized on StockItem, so this is
    always consistent but re-scans all movements for the item each time it's called."""
    movements = item.movements
    stock_in = movements.filter(movement_type=MovementType.IN).aggregate(total=Sum('quantity'))['total'] or 0
    stock_out = movements.filter(movement_type=MovementType.OUT).aggregate(total=Sum('quantity'))['total'] or 0
    return stock_in - stock_out
