from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.core.permissions import IsAdminOrTechnician
from apps.maintenance.models import EquipmentFault, UnusualCase
from apps.maintenance.serializers import EquipmentFaultSerializer, UnusualCaseSerializer


class EquipmentFaultListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/equipment-faults/ — list/declare equipment faults for the farm's houses.
    Declaring a fault reserved to Technician / Admin (section 8)."""

    serializer_class = EquipmentFaultSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminOrTechnician()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return EquipmentFault.objects.filter(house__farm=self.request.user.farm)


class UnusualCaseListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/unusual-cases/ — list/report unusual observations on a batch.
    Open to any authenticated user of the farm for both listing and creation (no role
    restriction is applied here, unlike most other write endpoints)."""

    serializer_class = UnusualCaseSerializer

    def get_queryset(self):
        return UnusualCase.objects.filter(batch__house__farm=self.request.user.farm)
