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

from apps.core.column_matching import match_columns
from apps.core.xlsx import (
    WorkbookError, as_bool, as_number, build_workbook, cell_getter, clean, open_rows,
)
from apps.stock.import_columns import COLUMNS
from apps.stock.models import FeedStage, StockCategory, StockItem, Supplier
from apps.stock.serializers import _KIND_PREFIX  # noqa: F401 (used via next_free_item_code)
from apps.stock.serializers import StockItemSerializer, next_free_item_code
from rest_framework import serializers

# Exact French headers the template ships with. Accepted spellings beyond these live in
# apps/stock/import_columns.py.
HEADERS = [c.label for c in COLUMNS]

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


def parse_and_apply_stock_import(farm, file_obj, dry_run=False) -> dict:
    """Update-or-create StockItem parameters from an .xlsx.

    Headers are resolved by the shared matcher (synonyms + edit distance), so a file whose
    columns don't match the template still imports — see apps/core/column_matching.py.

    `dry_run=True` reports what *would* happen (and the column mapping) without writing
    anything, for the preview the batch-creation screen shows before committing.
    """
    header, rows_iter = open_rows(file_obj)
    report = match_columns(header, COLUMNS)
    index = report.index

    if report.unresolved:
        if dry_run:
            # Let the preview point at the column that needs attention rather than failing
            # with a message the user can't act on column by column.
            return {'updated': 0, 'created': 0, 'skipped': [], 'columns': report.as_dict(), 'dryRun': True}
        raise WorkbookError(
            'En-têtes de colonnes introuvables : '
            + ', '.join(f'« {m.label} »' for m in report.unresolved)
            + '. Téléchargez le modèle et conservez la première ligne.'
        )

    get = cell_getter(index)

    if dry_run:
        # Run the real import and roll it back, so the preview counts and skip reasons come
        # from the same code that will commit — a separately-written "what would happen"
        # branch is exactly the thing that drifts from the real one.
        try:
            with transaction.atomic():
                result = _import_rows(farm, rows_iter, get, report)
                raise _DryRunRollback(result)
        except _DryRunRollback as stop:
            return {**stop.result, 'dryRun': True}

    return _import_rows(farm, rows_iter, get, report)


class _ResolvedRelatedField(serializers.PrimaryKeyRelatedField):
    """Accepts the category / supplier instance the importer already resolved (farm-scoped by
    `_resolve_category` / `_resolve_supplier`) instead of re-fetching it by primary key: at 2,000
    rows those two lookups were a third of the import's queries."""

    def to_internal_value(self, data):
        if isinstance(data, self.get_queryset().model):
            return data
        return super().to_internal_value(data)


class _ImportStockItemSerializer(StockItemSerializer):
    category = _ResolvedRelatedField(queryset=StockCategory.objects.all())
    supplier = _ResolvedRelatedField(queryset=Supplier.objects.all(), required=False, allow_null=True)


class _DryRunRollback(Exception):
    """Carries the would-be result out of the transaction that is being rolled back."""

    def __init__(self, result):
        super().__init__('dry run')
        self.result = result


def _import_rows(farm, rows_iter, get, report) -> dict:
    cat_cache, sup_cache = {}, {}
    used_codes = set(StockItem.objects.filter(farm=farm).values_list('item_code', flat=True))
    # One query for every existing article instead of one per row. Keyed like `name__iexact`;
    # the first row per name wins, as `.first()` did.
    items_by_name = {}
    for item in StockItem.objects.filter(farm=farm).order_by('pk'):
        items_by_name.setdefault(item.name.lower(), item)
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
        # A cell that holds something but not a number is reported: turning it into 0 overwrote
        # an existing item's price and called the row a success. Blank still means 0 (documented).
        threshold, threshold_error = _number_cell(get(raw, 'alert_threshold'), "seuil d'alerte")
        price, price_error = _number_cell(get(raw, 'unit_price'), 'prix unitaire')
        if threshold_error or price_error:
            skipped.append({'line': line, 'reason': threshold_error or price_error})
            continue

        existing = items_by_name.get(name.lower())
        unit = clean(get(raw, 'unit'))
        if existing is None and not unit:
            skipped.append({'line': line, 'reason': 'unité manquante'})
            continue

        # Snapshot the caches: a category or supplier created inside this row's savepoint is
        # rolled back with the row, and a cached reference to it made every later row of the
        # same new category fail on a primary key that no longer existed.
        cat_before, sup_before = dict(cat_cache), dict(sup_cache)
        try:
            with transaction.atomic():
                category = _resolve_category(farm, category_label, cat_cache)
                fields = {
                    'category': category,
                    'alert_threshold': threshold,
                    'unit_price': _to_decimal(price),
                    **_detail_fields(category.kind, get(raw, 'detail')),
                }
                # A blank or absent Unité leaves an existing item's unit alone (a new item without
                # one was skipped above); an absent Fournisseur column leaves its supplier alone —
                # both as the columns' preview notes promise. A present, blank Fournisseur clears it.
                if unit:
                    fields['unit'] = unit
                if 'supplier' in report.index or existing is None:
                    supplier = _resolve_supplier(farm, clean(get(raw, 'supplier')), sup_cache)
                    fields['supplier'] = supplier

                if existing:
                    # Parameter update only — StockItemSerializer has no quantity field, so a
                    # partial update cannot touch stock level / StockMovement history.
                    ser = _ImportStockItemSerializer(existing, data=fields, partial=True)
                    ser.is_valid(raise_exception=True)
                    ser.save()
                    updated += 1
                else:
                    code = next_free_item_code(farm.id, category, used_codes)
                    ser = _ImportStockItemSerializer(data={**fields, 'name': name})
                    ser.is_valid(raise_exception=True)
                    items_by_name[name.lower()] = ser.save(farm=farm, item_code=code)
                    used_codes.add(code)
                    created += 1
        except Exception as exc:  # serializer ValidationError, integrity, etc. — skip this row
            if existing is not None:
                # The failed update already assigned this row's values onto the cached instance;
                # re-read it so a later row naming the same article doesn't save them after all.
                items_by_name[name.lower()] = StockItem.objects.filter(pk=existing.pk).first()
            cat_cache.clear()
            cat_cache.update(cat_before)
            sup_cache.clear()
            sup_cache.update(sup_before)
            skipped.append({'line': line, 'reason': _reason(exc)})

    return {'updated': updated, 'created': created, 'skipped': skipped, 'columns': report.as_dict()}


def _number_cell(value, label):
    """(number, None) for a number or a blank cell (blank -> 0, as documented); (None, reason)
    for a cell holding text that is not a number."""
    if clean(value) == '':
        return 0, None
    number = as_number(value)
    if number is None:
        return None, f'{label} illisible : « {clean(value)} »'
    return number, None


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
