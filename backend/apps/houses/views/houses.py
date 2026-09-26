from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

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

    def destroy(self, request, *args, **kwargs):
        # Deleting a house CASCADEs its batches with their daily logs, weighings, task
        # completions and closing report, and unlinks their sales and stock movements. With an
        # ACTIVE batch that is a live flock's whole history gone in one request, with no trace
        # (campaign 9, finding B8). A running flock is closed first; an empty house (or one whose
        # batches are all closed) is still deletable.
        from apps.batches.models import BatchStatus

        house = self.get_object()
        if house.batches.filter(status=BatchStatus.ACTIVE).exists():
            return Response(
                {'detail': "Ce bâtiment a une bande en cours : clôturez-la avant de supprimer le bâtiment."},
                status=status.HTTP_409_CONFLICT,
            )
        return super().destroy(request, *args, **kwargs)
