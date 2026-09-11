"""Farm-wide overview for the "Bilan global" tree view.

Three branch statuses (santé / finances / stock) plus one combined core status. Every rule is
deterministic and computed from data the app already stores — no scoring model, no external
call. The tiers are the same three the rest of the app already uses: `good` / `watch` /
`critical`.

ALL TUNABLE THRESHOLDS LIVE IN THIS FILE, in the block below. Change them here and both the
API and the tree view follow; nothing else hardcodes a number.

The santé branch deliberately delegates to `apps.batches.calculations.farm_health_score`
rather than re-deriving mortality rules: that function is already the documented farm health
badge (mortality trend, FCR trend, open alerts), and a second, slightly-different health rule
in a second place is how two screens start disagreeing about the same farm.
"""
from apps.batches.calculations import farm_health_score
from apps.finance.calculations import cash_on_hand, monthly_summary
from apps.stock.calculations import current_quantity

# ---------------------------------------------------------------------------
# Thresholds — proposed defaults, documented so they can be reviewed and tuned.
# ---------------------------------------------------------------------------

#: Stock. An article is "low" when its quantity is at or under its own `alert_threshold`
#: (the per-article reorder level the user already sets — not a number invented here).
#: `critical` when any article has actually run out, or when this many articles are low at
#: once; `watch` as soon as one is low.
STOCK_LOW_COUNT_FOR_CRITICAL = 3
STOCK_EMPTY_QUANTITY = 0

#: Finances. `critical` when the cash position is negative — the farm is spending money it
#: does not have. `watch` when it is positive but under this floor, or when the most recent
#: complete month recorded expenses without a single sale. The floor is expressed in the app's
#: own bare money unit (the UI prints amounts with no currency symbol).
CASH_WATCH_FLOOR = 100_000
CASH_CRITICAL_BELOW = 0

#: How many months of history the finance branch summarises.
FINANCE_RANGE = '6m'

TIER_ORDER = {'good': 0, 'watch': 1, 'critical': 2}

CORE_LABELS = {
    'good': 'Ferme en bonne santé',
    'watch': 'Attention requise',
    'critical': 'Intervention urgente',
}


def _worst(tiers):
    return max(tiers, key=lambda t: TIER_ORDER.get(t, 0)) if tiers else 'good'


def stock_branch(farm):
    """Stock levels against each article's own reorder threshold."""
    from apps.stock.models import StockItem

    items = list(StockItem.objects.filter(farm=farm))
    low, empty = [], []
    for item in items:
        quantity = current_quantity(item)
        if quantity <= STOCK_EMPTY_QUANTITY:
            empty.append(item.name)
        if quantity <= (item.alert_threshold or 0):
            low.append(item.name)

    if empty or len(low) >= STOCK_LOW_COUNT_FOR_CRITICAL:
        tier = 'critical'
        message = (
            f'{len(empty)} article(s) épuisé(s)' if empty
            else f'{len(low)} articles sous leur seuil'
        )
    elif low:
        tier = 'watch'
        message = f'{len(low)} article(s) sous le seuil'
    else:
        tier = 'good'
        message = 'Niveaux suffisants'

    return {
        'tier': tier,
        'message': message,
        'value': len(items),
        'valueLabel': f'{len(items)} article(s) suivi(s)',
        'lowItems': low[:5],
    }


def finance_branch(farm):
    """Cash position, plus whether the latest month recorded any revenue at all."""
    cash = cash_on_hand(farm)
    months = monthly_summary(farm, FINANCE_RANGE)
    revenue = sum(m['revenue'] for m in months)
    latest = months[-1] if months else None
    barren_month = bool(latest and latest['revenue'] == 0 and latest['expenses'] > 0)

    if cash < CASH_CRITICAL_BELOW:
        tier, message = 'critical', 'Trésorerie négative'
    elif cash < CASH_WATCH_FLOOR or barren_month:
        tier = 'watch'
        message = 'Aucune vente le mois dernier' if barren_month else 'Trésorerie faible'
    else:
        tier, message = 'good', 'La ferme va bien financièrement'

    return {
        'tier': tier,
        'message': message,
        'value': round(revenue, 2),
        'valueLabel': 'Revenus sur 6 mois',
        'cash': round(cash, 2),
    }


def health_branch(farm):
    """Delegates to the existing farm health score (mortality trend, FCR trend, open alerts)."""
    from apps.batches.models import BatchStatus, PoultryBatch

    score = farm_health_score(farm)
    birds = sum(
        b.current_count
        for b in PoultryBatch.objects.filter(house__farm=farm, status=BatchStatus.ACTIVE)
    )
    return {
        'tier': score['tier'],
        'message': score.get('reason') or score.get('label') or '',
        'value': birds,
        'valueLabel': f'{birds} volaille(s) en élevage',
    }


def farm_overview(farm):
    """`{core: {...}, branches: {finance, stock, health}}` — the whole tree in one response."""
    branches = {
        'finance': finance_branch(farm),
        'stock': stock_branch(farm),
        'health': health_branch(farm),
    }
    tier = _worst([b['tier'] for b in branches.values()])
    weakest = [name for name, b in branches.items() if b['tier'] == tier]

    return {
        'core': {
            'tier': tier,
            'label': CORE_LABELS[tier],
            # Names the branch(es) that set the core status, so the headline is explainable
            # rather than a number the user has to take on faith.
            'drivers': weakest if tier != 'good' else [],
        },
        'branches': branches,
        'thresholds': {
            'stockLowCountForCritical': STOCK_LOW_COUNT_FOR_CRITICAL,
            'cashWatchFloor': CASH_WATCH_FLOOR,
            'financeRange': FINANCE_RANGE,
        },
    }
