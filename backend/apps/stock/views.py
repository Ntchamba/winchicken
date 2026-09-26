import math

from django.db import transaction
from django.db.models import Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.codes import create_with_code
from apps.core.models import Farm
from apps.core.permissions import IsAdminOrFarmManagerOrFarmer
from apps.core.services import record_audit_log
from apps.stock.calculations import current_quantity, is_low, with_current_quantity
from apps.stock.models import (
    StockCategory, StockComposition, StockItem, StockMovement, Supplier, Vaccination,
)
from apps.stock.serializers import (
    StockCategorySerializer, StockCompositionSerializer, StockItemRowSerializer, StockItemSerializer,
    StockMovementSerializer,
    SupplierSerializer, VaccinationSerializer, generate_item_code, next_free_item_code,
)

_StockItemsPayload = inline_serializer('StockItemsPayload', {'items': StockItemSerializer(many=True)})


def _scoped_farm(request, farm_id):
    """The requester's own farm, or 404 if the URL names any other one.

    Every /api/farms/<farm_id>/... endpoint used to `_scoped_farm(request, farm_id)` and
    scope its data to that id, never checking it was the caller's farm (security review
    2026-09-26, MEDIUM-6). The Farm singleton hides this today — a second farm cannot exist — but
    request.user.farm is the only farm any user may read or write, so resolve against it and
    treat a mismatch as "not found" (never confirm another farm id could exist).
    """
    farm = request.user.farm
    if farm is None or str(farm.pk) != str(farm_id):
        raise Http404()
    return farm

# Protocol category label → StockCategory.kind, for inline item creation from a protocol row
# ("+ Créer ... comme nouvel article de stock"): a Feeding-category row makes a FEED item, etc.
# Anything unmapped falls back to the farm's first StockCategory.
_PROTOCOL_LABEL_TO_KIND = {
    'alimentation': 'FEED',
    'vaccination': 'VETERINARY',
    'santé et soins': 'VETERINARY',
    'nettoyage': 'BEDDING',
    'température': 'EQUIPMENT',
}


_ROW_FIELD_LABELS = {
    'name': 'Nom', 'unit': 'Unité', 'item_type': 'Type', 'feed_stage': 'Stade',
    'cold_chain_required': 'Chaîne du froid', 'alert_threshold': "Seuil d'alerte", 'unit_price': 'Prix unitaire',
}


class FarmStockItemsView(APIView):
    """GET/PUT /api/farms/{farmId}/stock-items/ — read or save stock parameters.

    PUT is an **upsert** keyed on `item_code` (used by both the onboarding "Stock" step and
    /dashboard/stock): a row whose code already exists is updated in place, a row with no code
    is created, and only rows the client left out are deleted — all inside one transaction.

    It used to delete every row and recreate them, which silently destroyed everything pointing
    at a StockItem: its `StockMovement` history, its `PurchaseOrder`s, its `Vaccination` records
    and its `StockComposition` recipes (all CASCADE), and it severed `EquipmentFault.item` and
    `ProtocolTemplate.stock_item` (both SET_NULL). The last one stopped protocol-driven stock
    deduction dead — re-sending the same `item_code` did not save it, because the `delete()`
    nulled the FK before the row was recreated and a same-PK recreate does not restore it.
    Opening the form and pressing save without changing anything was enough (FIX 3.5, bug B).

    Editing reserved to Admin / Farm Manager /
    Farmer (`IsAdminOrFarmManagerOrFarmer`); GET is open to any authenticated user of the farm.

    Each item's `category` is a `StockCategory` id (must belong to this farm); `supplier` is an
    optional `Supplier` id (must belong to this farm) or null.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=_StockItemsPayload)
    def get(self, request, farm_id):
        farm = _scoped_farm(request, farm_id)
        items = with_current_quantity(StockItem.objects.filter(farm=farm).select_related('category', 'supplier'))
        return Response({'items': StockItemSerializer(items, many=True).data})

    @extend_schema(
        request=inline_serializer('StockItemCreate', {
            'name': serializers.CharField(),
            'unit': serializers.CharField(required=False),
            'category': serializers.IntegerField(required=False, help_text='StockCategory id; wins over category_hint.'),
            'category_hint': serializers.CharField(required=False, help_text="Protocol category label, e.g. 'Alimentation'."),
        }),
        responses={201: StockItemSerializer},
    )
    def post(self, request, farm_id):
        """Create ONE StockItem — used by the inline "+ Créer '{name}' comme nouvel article de
        stock" option in a protocol row's Consommation selector. `category` (a StockCategory id)
        wins; else `category_hint` (the row's protocol category label) maps to a kind; else the
        farm's first StockCategory. `unit` defaults to 'kg'. Same permission as PUT."""
        if not IsAdminOrFarmManagerOrFarmer().has_permission(request, self):
            return Response({'detail': 'Action non autorisée.'}, status=status.HTTP_403_FORBIDDEN)
        farm = _scoped_farm(request, farm_id)
        name = (request.data.get('name') or '').strip()
        if not name:
            return Response({'detail': "Le nom de l'article est requis."}, status=status.HTTP_400_BAD_REQUEST)
        # One article per name: "Créer « Provende »" for a name the farm already has links the
        # row to that article instead of creating a twin (the form offered it after a reload,
        # and the Excel import matches articles by name).
        existing_item = StockItem.objects.filter(farm=farm, name__iexact=name).first()
        if existing_item is not None:
            return Response(StockItemSerializer(existing_item).data, status=status.HTTP_200_OK)

        category = None
        cat_id = request.data.get('category')
        if cat_id not in (None, ''):
            category = StockCategory.objects.filter(farm=farm, pk=cat_id).first()
            if category is None:
                return Response({'detail': f'Catégorie invalide : {cat_id!r}.'}, status=status.HTTP_400_BAD_REQUEST)
        if category is None:
            kind = _PROTOCOL_LABEL_TO_KIND.get((request.data.get('category_hint') or '').strip().lower())
            if kind:
                category = StockCategory.objects.filter(farm=farm, kind=kind).order_by('sort_order', 'id').first()
        if category is None:
            category = StockCategory.objects.filter(farm=farm).order_by('sort_order', 'id').first()
        if category is None:
            return Response({'detail': 'Aucune catégorie de stock disponible.'}, status=status.HTTP_400_BAD_REQUEST)

        item = create_with_code(lambda: StockItem.objects.create(
            item_code=generate_item_code(farm.id, category),
            farm=farm, category=category, name=name, unit=(request.data.get('unit') or 'kg'),
            item_type=(request.data.get('item_type') or ''),
        ))
        record_audit_log(request.user, 'stock.item_created', item.name)
        return Response(StockItemSerializer(item).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=_StockItemsPayload, responses=_StockItemsPayload)
    def put(self, request, farm_id):
        if not IsAdminOrFarmManagerOrFarmer().has_permission(request, self):
            return Response({'detail': 'Action non autorisée.'}, status=status.HTTP_403_FORBIDDEN)
        farm = _scoped_farm(request, farm_id)
        items_data = request.data.get('items', [])

        categories = {c.id: c for c in StockCategory.objects.filter(farm=farm)}
        supplier_ids = set(Supplier.objects.filter(farm=farm).values_list('id', flat=True))

        # Each row's own values go through StockItemRowSerializer before anything is written.
        # They used to be read raw: a name over 255 characters or a price over 10^10 was a
        # DataError, a non-numeric threshold a ValueError, a row without a name a KeyError — 500
        # each — and a -50 threshold or -100 FCFA price was stored (campaign 9, finding B9).
        # Errors are keyed by row index, which the UI shows as "Ligne N : ...".
        row_errors, clean_rows = {}, []
        for index, entry in enumerate(items_data):
            row = StockItemRowSerializer(data={k: entry[k] for k in StockItemRowSerializer.Meta.fields if k in entry})
            if row.is_valid():
                clean_rows.append(row.validated_data)
            else:
                row_errors[str(index)] = row.errors
        if row_errors:
            # The form groups articles by category tab, so a flat "Ligne N" does not match anything
            # on screen — name the article and the field. A row already stored with a now-refused
            # value (a legacy negative price) blocks the save until corrected, so the message has
            # to say exactly which one.
            index, errors = next(iter(row_errors.items()))
            field, messages = next(iter(errors.items()))
            name = str(items_data[int(index)].get('name') or '').strip() or f'ligne {int(index) + 1}'
            label = _ROW_FIELD_LABELS.get(field, field)
            return Response(
                {'detail': f"Article « {name[:60]} » — {label} : {messages[0]}", 'items': row_errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        seen_names = set()
        for entry in items_data:
            key = (entry.get('name') or '').strip().lower()
            if key in seen_names:
                return Response(
                    {'detail': f"L'article « {entry['name'].strip()} » figure deux fois : chaque article doit avoir un nom unique."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            seen_names.add(key)

        with transaction.atomic():
            existing = {i.item_code: i for i in StockItem.objects.filter(farm=farm)}
            # Codes the client sent for rows it wants kept are authoritative and must not
            # change — StockMovement, PurchaseOrder, Vaccination, StockComposition and
            # ProtocolTemplate.stock_item all reference them. A row with no code is a new
            # article and gets one that avoids every code already taken or kept in this request.
            used_codes = set(existing) | {e['item_code'] for e in items_data if e.get('item_code')}
            kept_codes = set()
            for entry, values in zip(items_data, clean_rows):
                category = categories.get(entry.get('category'))
                if category is None:
                    return Response(
                        {'detail': f"Catégorie invalide : {entry.get('category')!r}."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                supplier_id = entry.get('supplier')
                if supplier_id is not None and supplier_id not in supplier_ids:
                    return Response(
                        {'detail': f'Fournisseur invalide : {supplier_id!r}.'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                fields = {
                    'category': category,
                    'name': values['name'],
                    'unit': values.get('unit', ''),
                    'item_type': values.get('item_type', '') or '',
                    'feed_stage': values.get('feed_stage', 'NOT_APPLICABLE'),
                    'cold_chain_required': values.get('cold_chain_required', False),
                    'alert_threshold': values.get('alert_threshold', 0),
                    'unit_price': values.get('unit_price', 0),
                    'supplier_id': supplier_id,
                }
                item = existing.get(entry.get('item_code'))
                if item is None:
                    item_code = entry.get('item_code')
                    if not item_code:
                        item_code = next_free_item_code(farm.id, category, used_codes)
                        used_codes.add(item_code)
                    item = StockItem.objects.create(item_code=item_code, farm=farm, **fields)
                else:
                    for field, value in fields.items():
                        setattr(item, field, value)
                    item.save()
                kept_codes.add(item.item_code)

            # Only rows the client actually left out are removed. Deleting one still cascades
            # to its movements, purchase orders, vaccinations and compositions — that is a
            # deletion the user asked for, unlike the old blanket delete of every row.
            StockItem.objects.filter(farm=farm).exclude(item_code__in=kept_codes).delete()
        record_audit_log(request.user, 'stock.updated', f'Paramètres de stock ({len(kept_codes)} article(s))')
        items = with_current_quantity(StockItem.objects.filter(farm=farm).select_related('category', 'supplier'))
        return Response({'items': StockItemSerializer(items, many=True).data})


class FarmStockCategoriesView(generics.ListCreateAPIView):
    """GET/POST /api/farms/{farmId}/stock-categories/ — list a farm's stock parameter tabs (the
    four defaults plus any custom ones), or add a new custom one. New categories are appended
    (`sort_order` = current max + 1) with `kind=CUSTOM`. Creation reserved to
    Admin/Farm Manager/Farmer; GET open to any authenticated user of the farm. Mirrors
    `apps.houses.views.protocol.ProtocolCategoryListCreateView`."""

    serializer_class = StockCategorySerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminOrFarmManagerOrFarmer()]
        return [IsAuthenticated()]

    def get_farm(self):
        return _scoped_farm(self.request, self.kwargs['farm_id'])

    def get_queryset(self):
        return StockCategory.objects.filter(farm=self.get_farm())

    def perform_create(self, serializer):
        from django.db.models import Max

        farm = self.get_farm()
        current_max = StockCategory.objects.filter(farm=farm).aggregate(Max('sort_order'))['sort_order__max']
        serializer.save(farm=farm, sort_order=(current_max + 1) if current_max is not None else 0)


class StockCategoryDetailView(generics.DestroyAPIView):
    """DELETE /api/stock-categories/{id}/ — removes one category (default or custom). Cascades to
    delete its StockItem rows (`StockItem.category` is `on_delete=CASCADE`) — the frontend
    confirm dialog says so explicitly. Reserved to Admin/Farm Manager/Farmer."""

    serializer_class = StockCategorySerializer
    permission_classes = [IsAdminOrFarmManagerOrFarmer]
    lookup_field = 'pk'

    def get_queryset(self):
        return StockCategory.objects.filter(farm=self.request.user.farm)


class FarmSuppliersView(generics.ListCreateAPIView):
    """GET/POST /api/farms/{farmId}/suppliers/ — the farm's supplier directory. GET open to any
    authenticated user of the farm; POST reserved to Admin/Farm Manager/Farmer, consistent with
    who manages stock parameters."""

    serializer_class = SupplierSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminOrFarmManagerOrFarmer()]
        return [IsAuthenticated()]

    def get_farm(self):
        return _scoped_farm(self.request, self.kwargs['farm_id'])

    def get_queryset(self):
        return Supplier.objects.filter(farm=self.get_farm()).prefetch_related('items')

    def perform_create(self, serializer):
        serializer.save(farm=self.get_farm())


def _ingredient_items_with_quantity():
    """Each ingredient's item with its on-hand quantity already computed — the ingredient rows
    show it, and reading it item by item was two queries per ingredient."""
    return Prefetch('ingredients__item', queryset=with_current_quantity(StockItem.objects.all()))


class FarmStockCompositionsView(generics.ListCreateAPIView):
    """GET/POST /api/farms/{farmId}/stock-compositions/ — the farm's composition "recipes".
    GET open to any farm user; POST reserved to Admin/Farm Manager/Farmer. POST creates the
    composition + its ingredient rows in one transaction and writes NO StockMovement (that
    happens only on Exécuter, see StockCompositionExecuteView)."""

    serializer_class = StockCompositionSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminOrFarmManagerOrFarmer()]
        return [IsAuthenticated()]

    def get_farm(self):
        return _scoped_farm(self.request, self.kwargs['farm_id'])

    def get_queryset(self):
        return (
            StockComposition.objects.filter(farm=self.get_farm())
            .select_related('output_item')
            .prefetch_related(_ingredient_items_with_quantity())
        )

    def perform_create(self, serializer):
        farm = self.get_farm()
        data = serializer.validated_data
        farm_item_codes = set(StockItem.objects.filter(farm=farm).values_list('item_code', flat=True))
        codes = {data['output_item'].item_code} | {ing['item'].item_code for ing in data['ingredients']}
        if not codes <= farm_item_codes:
            raise serializers.ValidationError({'detail': 'Un article référencé n’appartient pas à cette ferme.'})
        serializer.save(farm=farm)


class StockCompositionDetailView(generics.RetrieveDestroyAPIView):
    """GET/PATCH/DELETE /api/stock-compositions/{id}/. PATCH (Admin/Farm Manager/Farmer) is a
    light update of `base_output_quantity` only — the "rendement de base" that gates the
    add-stock auto-deduction; ingredients/name/output are not editable here (delete + recreate).
    DELETE reserved to Admin/Farm Manager/Farmer; removes the recipe only — StockMovements from
    past executions are untouched."""

    serializer_class = StockCompositionSerializer
    lookup_field = 'pk'

    def get_permissions(self):
        if self.request.method in ('DELETE', 'PATCH'):
            return [IsAdminOrFarmManagerOrFarmer()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return (
            StockComposition.objects.filter(farm=self.request.user.farm)
            .select_related('output_item').prefetch_related(_ingredient_items_with_quantity())
        )

    def patch(self, request, *args, **kwargs):
        composition = self.get_object()
        if 'base_output_quantity' in request.data:
            raw = request.data.get('base_output_quantity')
            if raw in (None, ''):
                composition.base_output_quantity = None
            else:
                try:
                    value = float(raw)
                except (TypeError, ValueError):
                    return Response({'detail': 'Rendement de base invalide.'}, status=status.HTTP_400_BAD_REQUEST)
                if value <= 0:
                    return Response({'detail': 'Le rendement de base doit être positif.'}, status=status.HTTP_400_BAD_REQUEST)
                composition.base_output_quantity = value
            composition.save(update_fields=['base_output_quantity'])
        return Response(self.get_serializer(composition).data)


class StockCompositionExecuteView(APIView):
    """POST /api/stock-compositions/{id}/execute/ — run a composition. Body:
    `{ingredients: [{item, quantity}, ...], outputQuantity, force?}`. Per-ingredient quantities
    are editable (default to the recipe base); `outputQuantity` is user-entered, never summed
    from inputs. Non-blocking insufficient-stock check: a shortfall + no `force` returns
    `{status: 'insufficient_stock', shortfalls}` and writes nothing. Otherwise one transaction:
    one OUT per ingredient + one IN for the output, movement_date = today, batch = null.
    Reserved to Admin/Farm Manager/Farmer."""

    permission_classes = [IsAdminOrFarmManagerOrFarmer]

    @extend_schema(
        request=inline_serializer('StockCompositionExecute', {
            'ingredients': inline_serializer('StockCompositionExecuteIngredient', {
                'item': serializers.CharField(), 'quantity': serializers.FloatField(),
            }, many=True),
            'outputQuantity': serializers.FloatField(),
            'force': serializers.BooleanField(required=False),
        }),
        responses={200: inline_serializer('StockCompositionExecuteResult', {
            'status': serializers.ChoiceField(['done', 'insufficient_stock']),
            'shortfalls': serializers.ListField(child=serializers.DictField()),
            'movements': serializers.ListField(child=serializers.IntegerField(), required=False),
        })},
    )
    def post(self, request, pk):
        from apps.stock.compositions import execute_composition

        composition = get_object_or_404(
            StockComposition.objects.select_related('output_item').prefetch_related('ingredients__item'),
            pk=pk, farm=request.user.farm,
        )
        result = execute_composition(
            composition,
            request.data.get('ingredients') or [],
            request.data.get('outputQuantity'),
            force=bool(request.data.get('force')),
        )
        return Response(result, status=result.pop('http_status', 200))


class SupplierDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE /api/suppliers/{id}/. Write reserved to Admin/Farm Manager/Farmer."""

    serializer_class = SupplierSerializer
    lookup_field = 'pk'

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH', 'DELETE'):
            return [IsAdminOrFarmManagerOrFarmer()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return Supplier.objects.filter(farm=self.request.user.farm).prefetch_related('items')


class StockItemDetailView(APIView):
    """PATCH /api/stock-items/{itemCode}/ — light single-item update (`unit`, `name` only).
    Used right after inline-creating an item from a protocol row's Consommation selector, so the
    user can set its unit there instead of visiting the Stock screen. Write reserved to
    Admin/Farm Manager/Farmer; `item_code`, `category`, quantities are not editable here."""

    permission_classes = [IsAdminOrFarmManagerOrFarmer]

    @extend_schema(
        request=inline_serializer('StockItemPatch', {
            'unit': serializers.CharField(required=False),
            'name': serializers.CharField(required=False),
        }),
        responses={200: StockItemSerializer},
    )
    def patch(self, request, item_code):
        item = get_object_or_404(StockItem, item_code=item_code, farm=request.user.farm)
        dirty = []
        if 'unit' in request.data:
            item.unit = (request.data.get('unit') or '').strip()
            dirty.append('unit')
        if request.data.get('name'):
            item.name = request.data['name'].strip()
            dirty.append('name')
        if dirty:
            item.save(update_fields=dirty)
        return Response(StockItemSerializer(item).data)


class FarmStockEvolutionView(APIView):
    """GET /api/farms/{farmId}/stock-evolution/ — per-item running-balance series for the stock
    evolution charts (calendar date, not day-of-cycle: stock isn't batch-scoped). See
    `apps.stock.calculations.stock_evolution`."""

    permission_classes = [IsAuthenticated]

    def get(self, request, farm_id):
        from apps.stock.calculations import stock_evolution

        farm = _scoped_farm(request, farm_id)
        return Response(stock_evolution(farm))


class StockItemCoverageView(APIView):
    """GET /api/stock-items/{itemCode}/coverage/?days=<span>&(quantity_per_day=<n>|dose_per_bird=<n>)
    — feeds the inline "stock insuffisant" warning in the protocol form. Pass `quantity_per_day`
    for "Quantité fixe / jour" mode or `dose_per_bird` for "Dose par bande" mode (the latter is
    multiplied by the farm's current live-bird count server-side). Non-blocking planning figure;
    see `apps.stock.calculations.coverage_for`."""

    permission_classes = [IsAuthenticated]

    def get(self, request, item_code):
        from apps.stock.calculations import coverage_for

        item = get_object_or_404(StockItem, item_code=item_code, farm=request.user.farm)
        raw_dose = request.query_params.get('dose_per_bird')
        try:
            quantity_per_day = float(request.query_params.get('quantity_per_day', 0) or 0)
            dose_per_bird = float(raw_dose) if raw_dose not in (None, '') else None
            days = int(request.query_params.get('days', 0) or 0)
            if not all(math.isfinite(v) for v in (quantity_per_day, dose_per_bird or 0)):
                raise ValueError('non-finite')
        except (TypeError, ValueError):
            return Response(
                {'detail': 'quantity_per_day, dose_per_bird et days doivent être numériques.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(coverage_for(item, quantity_per_day, days, dose_per_bird=dose_per_bird))


class StockItemsLowCountView(APIView):
    """GET /api/stock-items/low-count/ — sidebar Stock badge. Reuses
    apps.stock.calculations.current_quantity, the same on-hand-quantity computation the stock
    levels chart/LOW_STOCK alert already use, rather than a second implementation of the
    IN-minus-OUT aggregation."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = with_current_quantity(StockItem.objects.filter(farm=request.user.farm))
        count = sum(1 for item in items if is_low(current_quantity(item), item.alert_threshold))
        return Response({'count': count})


class StockMovementListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/stock-movements/ — history and creation of stock IN/OUT movements.
    Creation reserved to Admin / Farm Manager / Farmer.

    When the POST body carries `total_price` (the "Prix total payé" on a manual IN), the
    movement and a matching `Expense` are written in one transaction (see
    `apps.stock.purchasing`) — the Expense is what surfaces the purchase in Finance."""

    serializer_class = StockMovementSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminOrFarmManagerOrFarmer()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return StockMovement.objects.filter(item__farm=self.request.user.farm)

    def perform_create(self, serializer):
        from apps.stock.compositions import auto_deduct_ingredients_for_output
        from apps.stock.models import MovementType
        from apps.stock.purchasing import record_manual_purchase_expense

        total_price = serializer.validated_data.get('total_price')
        production_quantity = serializer.validated_data.get('production_quantity')
        self._composition_deduction = None
        with transaction.atomic():
            movement = serializer.save()
            if movement.movement_type == MovementType.IN:
                if total_price:
                    record_manual_purchase_expense(movement, total_price)
                if production_quantity:
                    result = auto_deduct_ingredients_for_output(
                        movement.item, production_quantity, movement.movement_date,
                    )
                    if result.get('status') == 'done':
                        self._composition_deduction = result

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        if getattr(self, '_composition_deduction', None):
            response.data['composition_deduction'] = self._composition_deduction
        return response


class VaccinationListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/vaccinations/ — history and creation of vaccination events."""

    serializer_class = VaccinationSerializer

    def get_queryset(self):
        return Vaccination.objects.filter(batch__house__farm=self.request.user.farm)


class StockImportTemplateView(APIView):
    """GET /api/stock-items/import-template.xlsx — the ready-to-fill Stock import template.
    AllowAny (static example content) so the frontend offers it as a plain download link."""

    permission_classes = [AllowAny]

    def get(self, request):
        from apps.stock.xlsx_import import build_stock_template
        from apps.core.xlsx import xlsx_download
        return xlsx_download(build_stock_template(), 'modele-stock.xlsx')


class StockImportView(APIView):
    """POST /api/farms/{farmId}/stock-items/import-xlsx/ (multipart, field `file`) — update-or-
    create StockItem parameters by Article name. Never deletes; never creates a StockMovement.
    Admin / Farm Manager / Farmer. Returns {updated, created, skipped:[{line, reason}]}."""

    permission_classes = [IsAdminOrFarmManagerOrFarmer]
    parser_classes = [MultiPartParser, FormParser]
    throttle_scope = 'import'  # security review 2026-09-26 HIGH-2

    def post(self, request, farm_id):
        from apps.stock.xlsx_import import parse_and_apply_stock_import
        from apps.core.xlsx import WorkbookError, check_upload_size

        farm = _scoped_farm(request, farm_id)
        upload = request.FILES.get('file')
        if upload is None:
            return Response({'detail': 'Aucun fichier reçu.'}, status=status.HTTP_400_BAD_REQUEST)
        if not upload.name.lower().endswith('.xlsx'):
            return Response({'detail': 'Importez un fichier .xlsx (Excel).'}, status=status.HTTP_400_BAD_REQUEST)
        # `dry_run=1` (the batch-creation preview) reports the column mapping and what would
        # change, and writes nothing — the user confirms before anything is committed.
        dry_run = str(request.data.get('dry_run', '')).lower() in ('1', 'true', 'oui')
        try:
            check_upload_size(upload)  # security review 2026-09-26: refuse a memory bomb up front
            result = parse_and_apply_stock_import(farm, upload, dry_run=dry_run)
        except WorkbookError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if dry_run:
            return Response(result)
        record_audit_log(
            request.user, 'stock.imported',
            f"Import stock ({result['updated']} maj, {result['created']} créé(s))",
        )
        return Response(result)
