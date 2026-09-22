from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import Farm
from apps.core.permissions import CanAdministerVaccination, IsAdminOrFarmManagerOrFarmer
from apps.stock.models import StockItem, StockMovement, Vaccination
from apps.stock.serializers import StockItemSerializer, StockMovementSerializer, VaccinationSerializer, generate_item_code

_StockItemsPayload = inline_serializer('StockItemsPayload', {'items': StockItemSerializer(many=True)})


class FarmStockItemsView(APIView):
    """GET/PUT /api/farms/{farmId}/stock-items/ — read or fully replace stock parameters.

    PUT is a full replace, not a merge (used by both the onboarding "Stock" step and
    /dashboard/stock): existing StockItem rows for the farm are deleted and recreated from the
    submitted `items` list inside one transaction. Editing reserved to Admin / Farm Manager /
    Farmer (`IsAdminOrFarmManagerOrFarmer`); GET is open to any authenticated user of the farm.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=_StockItemsPayload)
    def get(self, request, farm_id):
        farm = get_object_or_404(Farm, pk=farm_id)
        items = StockItem.objects.filter(farm=farm)
        return Response({'items': StockItemSerializer(items, many=True).data})

    @extend_schema(request=_StockItemsPayload, responses=_StockItemsPayload)
    def put(self, request, farm_id):
        if not IsAdminOrFarmManagerOrFarmer().has_permission(request, self):
            return Response({'detail': 'Action non autorisée.'}, status=status.HTTP_403_FORBIDDEN)
        farm = get_object_or_404(Farm, pk=farm_id)
        items_data = request.data.get('items', [])
        with transaction.atomic():
            StockItem.objects.filter(farm=farm).delete()
            created = []
            for entry in items_data:
                item_code = entry.get('item_code') or generate_item_code(farm.id, entry['category'])
                created.append(StockItem(
                    item_code=item_code,
                    farm=farm,
                    category=entry['category'],
                    name=entry['name'],
                    unit=entry.get('unit', ''),
                    feed_stage=entry.get('feed_stage', 'NOT_APPLICABLE'),
                    cold_chain_required=entry.get('cold_chain_required', False),
                    alert_threshold=entry.get('alert_threshold', 0),
                    unit_price=entry.get('unit_price', 0),
                ))
            StockItem.objects.bulk_create(created)
        return Response({'items': StockItemSerializer(StockItem.objects.filter(farm=farm), many=True).data})


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
    """GET/POST /api/vaccinations/ — history and creation of vaccination events.
    Recording a vaccination (a clinical action) is reserved to Admin / Farm Manager /
    Farmer / Technician."""

    serializer_class = VaccinationSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [CanAdministerVaccination()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return Vaccination.objects.filter(batch__house__farm=self.request.user.farm)
