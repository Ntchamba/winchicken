from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import Farm
from apps.core.permissions import IsAdminOrFarmManagerOrFarmer
from apps.core.services import record_audit_log
from apps.stock.calculations import current_quantity
from apps.stock.models import StockCategory, StockItem, StockMovement, Supplier, Vaccination
from apps.stock.serializers import (
    StockCategorySerializer, StockItemSerializer, StockMovementSerializer, SupplierSerializer,
    VaccinationSerializer, generate_item_code,
)

_StockItemsPayload = inline_serializer('StockItemsPayload', {'items': StockItemSerializer(many=True)})


class FarmStockItemsView(APIView):
    """GET/PUT /api/farms/{farmId}/stock-items/ — read or fully replace stock parameters.

    PUT is a full replace, not a merge (used by both the onboarding "Stock" step and
    /dashboard/stock): existing StockItem rows for the farm are deleted and recreated from the
    submitted `items` list inside one transaction. Editing reserved to Admin / Farm Manager /
    Farmer (`IsAdminOrFarmManagerOrFarmer`); GET is open to any authenticated user of the farm.

    Each item's `category` is a `StockCategory` id (must belong to this farm); `supplier` is an
    optional `Supplier` id (must belong to this farm) or null.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=_StockItemsPayload)
    def get(self, request, farm_id):
        farm = get_object_or_404(Farm, pk=farm_id)
        items = StockItem.objects.filter(farm=farm).select_related('category', 'supplier')
        return Response({'items': StockItemSerializer(items, many=True).data})

    @extend_schema(request=_StockItemsPayload, responses=_StockItemsPayload)
    def put(self, request, farm_id):
        if not IsAdminOrFarmManagerOrFarmer().has_permission(request, self):
            return Response({'detail': 'Action non autorisée.'}, status=status.HTTP_403_FORBIDDEN)
        farm = get_object_or_404(Farm, pk=farm_id)
        items_data = request.data.get('items', [])

        categories = {c.id: c for c in StockCategory.objects.filter(farm=farm)}
        supplier_ids = set(Supplier.objects.filter(farm=farm).values_list('id', flat=True))

        with transaction.atomic():
            StockItem.objects.filter(farm=farm).delete()
            created = []
            for entry in items_data:
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
                item_code = entry.get('item_code') or generate_item_code(farm.id, category)
                created.append(StockItem(
                    item_code=item_code,
                    farm=farm,
                    category=category,
                    name=entry['name'],
                    unit=entry.get('unit', ''),
                    feed_stage=entry.get('feed_stage', 'NOT_APPLICABLE'),
                    cold_chain_required=entry.get('cold_chain_required', False),
                    alert_threshold=entry.get('alert_threshold', 0),
                    unit_price=entry.get('unit_price', 0),
                    supplier_id=supplier_id,
                ))
            StockItem.objects.bulk_create(created)
        record_audit_log(request.user, 'stock.updated', f'Paramètres de stock ({len(created)} article(s))')
        items = StockItem.objects.filter(farm=farm).select_related('category', 'supplier')
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
        return get_object_or_404(Farm, pk=self.kwargs['farm_id'])

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
        return get_object_or_404(Farm, pk=self.kwargs['farm_id'])

    def get_queryset(self):
        return Supplier.objects.filter(farm=self.get_farm()).prefetch_related('items')

    def perform_create(self, serializer):
        serializer.save(farm=self.get_farm())


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


class FarmStockEvolutionView(APIView):
    """GET /api/farms/{farmId}/stock-evolution/ — per-item running-balance series for the stock
    evolution charts (calendar date, not day-of-cycle: stock isn't batch-scoped). See
    `apps.stock.calculations.stock_evolution`."""

    permission_classes = [IsAuthenticated]

    def get(self, request, farm_id):
        from apps.stock.calculations import stock_evolution

        farm = get_object_or_404(Farm, pk=farm_id)
        return Response(stock_evolution(farm))


class StockItemCoverageView(APIView):
    """GET /api/stock-items/{itemCode}/coverage/?quantity_per_day=<n>&days=<span> — feeds the
    inline "stock insuffisant" warning in the protocol form. Non-blocking planning figure; see
    `apps.stock.calculations.coverage_for`."""

    permission_classes = [IsAuthenticated]

    def get(self, request, item_code):
        from apps.stock.calculations import coverage_for

        item = get_object_or_404(StockItem, item_code=item_code, farm=request.user.farm)
        try:
            quantity_per_day = float(request.query_params.get('quantity_per_day', 0) or 0)
            days = int(request.query_params.get('days', 0) or 0)
        except (TypeError, ValueError):
            return Response({'detail': 'quantity_per_day et days doivent être numériques.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(coverage_for(item, quantity_per_day, days))


class StockItemsLowCountView(APIView):
    """GET /api/stock-items/low-count/ — sidebar Stock badge. Reuses
    apps.stock.calculations.current_quantity, the same on-hand-quantity computation the stock
    levels chart/LOW_STOCK alert already use, rather than a second implementation of the
    IN-minus-OUT aggregation."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = StockItem.objects.filter(farm=request.user.farm)
        count = sum(1 for item in items if current_quantity(item) <= item.alert_threshold)
        return Response({'count': count})


class StockMovementListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/stock-movements/ — history and creation of stock IN/OUT movements.
    Creation reserved to Admin / Farm Manager / Farmer."""

    serializer_class = StockMovementSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminOrFarmManagerOrFarmer()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return StockMovement.objects.filter(item__farm=self.request.user.farm)


class VaccinationListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/vaccinations/ — history and creation of vaccination events."""

    serializer_class = VaccinationSerializer

    def get_queryset(self):
        return Vaccination.objects.filter(batch__house__farm=self.request.user.farm)
