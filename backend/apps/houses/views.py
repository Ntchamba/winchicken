from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import CanEditHouseProtocol, IsAdminOrFarmManager
from apps.houses.models import PoultryHouse
from apps.houses.serializers import PoultryHouseSerializer
from apps.protocols.models import ProtocolCategory, ProtocolTemplate
from apps.protocols.serializers import ProtocolCategorySerializer, ProtocolTemplateSerializer


class HouseListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/houses/ — list the farm's houses, or create a new one.
    House creation reserved to Admin / Farm Manager (section 8); listing is open to any
    authenticated user of the farm."""

    serializer_class = PoultryHouseSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminOrFarmManager()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return PoultryHouse.objects.filter(farm=self.request.user.farm)


class HouseDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/houses/{houseCode}/ — view, edit or delete one house.
    PATCH/DELETE reserved to Admin / Farm Manager (section 8)."""

    serializer_class = PoultryHouseSerializer
    lookup_field = 'house_code'

    def get_permissions(self):
        if self.request.method in ('PATCH', 'PUT', 'DELETE'):
            return [IsAdminOrFarmManager()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return PoultryHouse.objects.filter(farm=self.request.user.farm)


class HouseProtocolView(APIView):
    """GET/PUT /api/houses/{houseCode}/protocol/ — read or fully replace a house's protocol lines.

    PUT is a full replace, not a merge: existing ProtocolTemplate rows for the house are deleted
    and recreated from the submitted `lines` list inside one transaction. Editing reserved to
    Admin / Farm Manager / the Farmer responsible for the house (`CanEditHouseProtocol`); GET is
    open to any authenticated user of the farm.
    """

    permission_classes = [IsAuthenticated]

    def get_house(self, house_code, farm):
        return get_object_or_404(PoultryHouse, house_code=house_code, farm=farm)

    @extend_schema(responses=ProtocolTemplateSerializer(many=True))
    def get(self, request, house_code):
        house = self.get_house(house_code, request.user.farm)
        lines = ProtocolTemplate.objects.filter(house=house)
        return Response(ProtocolTemplateSerializer(lines, many=True).data)

    @extend_schema(
        request=inline_serializer('HouseProtocolReplaceRequest', {'lines': ProtocolTemplateSerializer(many=True)}),
        responses=ProtocolTemplateSerializer(many=True),
    )
    def put(self, request, house_code):
        if not CanEditHouseProtocol().has_permission(request, self):
            return Response({'detail': 'Action non autorisée.'}, status=status.HTTP_403_FORBIDDEN)
        house = self.get_house(house_code, request.user.farm)
        lines = request.data.get('lines', [])
        serializer = ProtocolTemplateSerializer(data=lines, many=True)
        serializer.is_valid(raise_exception=True)

        # `category` resolves to a real ProtocolCategory instance via PrimaryKeyRelatedField —
        # the FK's existence is validated by DRF already, but not that it belongs to *this*
        # house. A category id from a different house (or farm) must be rejected here, not
        # silently accepted.
        for line in serializer.validated_data:
            if line['category'].house_id != house.house_code:
                return Response(
                    {'detail': "Une catégorie référencée n'appartient pas à ce bâtiment."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        with transaction.atomic():
            ProtocolTemplate.objects.filter(house=house).delete()
            ProtocolTemplate.objects.bulk_create([ProtocolTemplate(house=house, **line) for line in serializer.validated_data])
        return Response(ProtocolTemplateSerializer(ProtocolTemplate.objects.filter(house=house), many=True).data)


class ProtocolCategoryListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/houses/{houseCode}/protocol-categories/ — list a house's protocol tabs
    (the 5 defaults plus any custom ones), or add a new custom one. New categories are appended
    after the existing ones (`sort_order` = current max + 1). Creation reserved to
    Admin/Farm Manager/the Farmer responsible for the house, same as editing the protocol
    itself; GET is open to any authenticated user of the farm."""

    serializer_class = ProtocolCategorySerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [CanEditHouseProtocol()]
        return [IsAuthenticated()]

    def get_house(self):
        return get_object_or_404(PoultryHouse, house_code=self.kwargs['house_code'], farm=self.request.user.farm)

    def get_queryset(self):
        return ProtocolCategory.objects.filter(house=self.get_house())

    def perform_create(self, serializer):
        house = self.get_house()
        # max(sort_order) + 1, not count() — a deleted category would otherwise leave a gap
        # that count() could collide with an existing row's sort_order.
        from django.db.models import Max

        current_max = ProtocolCategory.objects.filter(house=house).aggregate(Max('sort_order'))['sort_order__max']
        serializer.save(house=house, sort_order=(current_max + 1) if current_max is not None else 0)


class ProtocolCategoryDetailView(generics.DestroyAPIView):
    """DELETE /api/houses/{houseCode}/protocol-categories/{id}/ — removes one category (default
    or custom). Cascades to delete its ProtocolTemplate rows (`ProtocolTemplate.category` is
    `on_delete=CASCADE`) — the frontend's confirm dialog says so explicitly before calling this.
    Reserved to Admin/Farm Manager/the Farmer responsible for the house."""

    serializer_class = ProtocolCategorySerializer
    permission_classes = [CanEditHouseProtocol]
    lookup_field = 'pk'

    def get_queryset(self):
        house = get_object_or_404(PoultryHouse, house_code=self.kwargs['house_code'], farm=self.request.user.farm)
        return ProtocolCategory.objects.filter(house=house)
