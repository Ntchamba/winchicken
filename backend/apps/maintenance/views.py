from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.core.permissions import IsAdminOrTechnician, IsFarmerOrWorker
from apps.maintenance.models import EquipmentFault, UnusualCase
from apps.maintenance.serializers import (
    EquipmentFaultSerializer,
    EquipmentFaultUpdateSerializer,
    UnusualCaseSerializer,
)


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


class EquipmentFaultDetailView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/equipment-faults/{faultCode}/ — read or move a fault's status
    (REPORTED -> IN_PROGRESS -> REPAIRED) and set `repaired_date`. Updating reserved to
    Technician / Admin, the same roles allowed to declare a fault (section 8: "Valider
    une tâche de maintenance")."""

    lookup_field = 'fault_code'
    lookup_url_kwarg = 'fault_code'

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'PUT'):
            return EquipmentFaultUpdateSerializer
        return EquipmentFaultSerializer

    def get_permissions(self):
        if self.request.method in ('PATCH', 'PUT'):
            return [IsAdminOrTechnician()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return EquipmentFault.objects.filter(house__farm=self.request.user.farm)


class UnusualCaseListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/unusual-cases/ — list/report unusual observations on a batch.
    Reporting a case reserved to Farmer / Worker (section 8); listing open to any
    authenticated user of the farm."""

    serializer_class = UnusualCaseSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsFarmerOrWorker()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return UnusualCase.objects.filter(batch__house__farm=self.request.user.farm)


class UnusualCaseDetailView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/unusual-cases/{caseCode}/ — read or edit a previously reported case.
    Editing reserved to Farmer / Worker, the same roles allowed to report one."""

    serializer_class = UnusualCaseSerializer
    lookup_field = 'case_code'
    lookup_url_kwarg = 'case_code'

    def get_permissions(self):
        if self.request.method in ('PATCH', 'PUT'):
            return [IsFarmerOrWorker()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return UnusualCase.objects.filter(batch__house__farm=self.request.user.farm)
