from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.core.permissions import IsAdminOrFarmManager
from apps.houses.models import PoultryHouse
from apps.houses.serializers import PoultryHouseSerializer


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
