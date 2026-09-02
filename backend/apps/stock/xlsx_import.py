"""Excel import for Stock parameters — update-or-create by Article name (docs/excel-import.md).

Unlike the Protocol import (full replacement), this NEVER deletes: a `StockItem` not named in
the file is left untouched. Matching an existing item updates only its parameters — category,
détail, unit, alert threshold, unit price, supplier — and never its quantity / `StockMovement`
history (this endpoint creates no movement). Categories and suppliers are matched by name
(case-insensitive) or auto-created via the same rules the "+" buttons use.
"""
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Max

from apps.core.xlsx import (
    WorkbookError, as_bool, as_number, build_workbook, cell_getter, clean,
    header_index, open_rows, require_headers,
)
from apps.stock.models import FeedStage, StockCategory, StockItem, Supplier
from apps.stock.serializers import _KIND_PREFIX  # noqa: F401 (used via next_free_item_code)
from apps.stock.serializers import StockItemSerializer, next_free_item_code

HEADERS = ['Article', 'Catégorie', 'Détail', 'Unité', 'Seuil d\'alerte', 'Prix unitaire', 'Fournisseur']
_ALIASES = {
    'article': 'name',
    'catégorie': 'category',
    'détail': 'detail',
    'unité': 'unit',
    "seuil d'alerte": 'alert_threshold',
    'prix unitaire': 'unit_price',
    'fournisseur': 'supplier',
}

EXAMPLE_ROWS = [
    ['Provende', 'Aliment', 'Starter', 'kg', 200, 450, 'Agrivet SARL'],
    ['Vaccin Newcastle', 'Vétérinaire', 'oui', 'flacon', 5, 3500, 'Pharmavet'],
    ['Abreuvoir', 'Équipement', 'Matériel d\'élevage', 'unité', 2, 12000, ''],
]

_FEED_STAGE_BY_TEXT = {}
for choice in FeedStage:
    _FEED_STAGE_BY_TEXT[choice.value.lower()] = choice.value
    _FEED_STAGE_BY_TEXT[choice.label.lower()] = choice.value


def build_stock_template() -> bytes:
    return build_workbook('Stock', HEADERS, EXAMPLE_ROWS)


def _resolve_category(farm, label, cache):
    """Match a StockCategory by label (case-insensitive) within the farm, else create a CUSTOM
    one — the exact rule FarmStockCategoriesView.perform_create uses (sort_order = max + 1)."""
    key = label.strip().lower()
    if key in cache:
        return cache[key]
    cat = StockCategory.objects.filter(farm=farm, label__iexact=label.strip()).first()
    if cat is None:
        current_max = StockCategory.objects.filter(farm=farm).aggregate(Max('sort_order'))['sort_order__max']
        cat = StockCategory.objects.create(
            farm=farm, label=label.strip(), icon='Package',
            sort_order=(current_max + 1) if current_max is not None else 0,
        )
    cache[key] = cat
    return cat


def _resolve_supplier(farm, name, cache):
    key = name.strip().lower()
    if not key:
        return None
    if key in cache:
        return cache[key]
    sup = Supplier.objects.filter(farm=farm, name__iexact=name.strip()).first()
    if sup is None:
        sup = Supplier.objects.create(farm=farm, name=name.strip())
    cache[key] = sup
    return sup


def _detail_fields(kind, detail_text):
    """The "Détail" column is polymorphic (matches the StockParametersForm UI):
    FEED -> feed_stage, VETERINARY -> cold_chain_required, otherwise -> item_type."""
    detail = clean(detail_text)
    if kind == 'FEED':
        return {'feed_stage': _FEED_STAGE_BY_TEXT.get(detail.lower(), FeedStage.NOT_APPLICABLE)}
    if kind == 'VETERINARY':
        return {'cold_chain_required': as_bool(detail)}
    return {'item_type': detail}


def parse_and_apply_stock_import(farm, file_obj) -> dict:
    header, rows_iter = open_rows(file_obj)
    index = header_index(header, _ALIASES)
    require_headers(index, [('Article', 'name'), ('Catégorie', 'category')])
    get = cell_getter(index)

    cat_cache, sup_cache = {}, {}
    used_codes = set(StockItem.objects.filter(farm=farm).values_list('item_code', flat=True))
    updated = created = 0
    skipped = []

    for line, raw in enumerate(rows_iter, start=2):
        if raw is None or all(clean(c) == '' for c in raw):
            continue

        name = clean(get(raw, 'name'))
        category_label = clean(get(raw, 'category'))
        if not name:
            skipped.append({'line': line, 'reason': "nom de l'article manquant"})
            continue
        if not category_label:
            skipped.append({'line': line, 'reason': 'catégorie manquante'})
            continue

        try:
            with transaction.atomic():
                category = _resolve_category(farm, category_label, cat_cache)
                supplier = _resolve_supplier(farm, clean(get(raw, 'supplier')), sup_cache)
                fields = {
                    'category': category.id,
                    'unit': clean(get(raw, 'unit')),
                    'alert_threshold': as_number(get(raw, 'alert_threshold')) or 0,
                    'unit_price': _to_decimal(get(raw, 'unit_price')),
                    'supplier': supplier.id if supplier else None,
                    **_detail_fields(category.kind, get(raw, 'detail')),
                }

                existing = StockItem.objects.filter(farm=farm, name__iexact=name).first()
                if existing:
                    # Parameter update only — StockItemSerializer has no quantity field, so a
                    # partial update cannot touch stock level / StockMovement history.
                    ser = StockItemSerializer(existing, data=fields, partial=True)
                    ser.is_valid(raise_exception=True)
                    ser.save()
                    updated += 1
                else:
                    code = next_free_item_code(farm.id, category, used_codes)
                    used_codes.add(code)
                    ser = StockItemSerializer(data={**fields, 'name': name})
                    ser.is_valid(raise_exception=True)
                    ser.save(farm=farm, item_code=code)
                    created += 1
        except Exception as exc:  # serializer ValidationError, integrity, etc. — skip this row
            skipped.append({'line': line, 'reason': _reason(exc)})

    return {'updated': updated, 'created': created, 'skipped': skipped}


def _to_decimal(value):
    n = as_number(value)
    if n is None:
        return Decimal('0')
    try:
        return Decimal(str(n))
    except InvalidOperation:
        return Decimal('0')


def _reason(exc):
    detail = getattr(exc, 'detail', None)
    if isinstance(detail, dict):
        first = next(iter(detail.values()))
        return str(first[0] if isinstance(first, list) else first)
    if isinstance(detail, list):
        return str(detail[0])
    return str(exc) or 'ligne invalide'
