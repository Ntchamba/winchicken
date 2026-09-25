from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsAdminOrFarmManager, IsAdminOrTechnician
from apps.core.services import record_audit_log
from apps.maintenance.models import EquipmentFault, UnusualCase
from apps.maintenance.serializers import EquipmentFaultSerializer, UnusualCaseSerializer


class EquipmentFaultListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/equipment-faults/ — list/declare equipment faults for the farm's houses.
    Declaring a fault reserved to Technician / Admin (section 8). `?status=OPEN` (2026-08-26,
    "Cas signalés") excludes resolved faults — `RESOLVED` is the only status value this app
    itself ever writes (via `EquipmentFaultResolveView` below), but `status` stays free-text
    (see model docstring), so this compares against that one literal rather than an enum choice
    list. `?house_code=` scopes to one house, for the per-house "Cas signalés" section."""

    serializer_class = EquipmentFaultSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminOrTechnician()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = EquipmentFault.objects.filter(house__farm=self.request.user.farm).select_related(
            'house', 'technician', 'resolved_by',
        )
        status_param = self.request.query_params.get('status')
        if status_param == 'OPEN':
            qs = qs.exclude(status='RESOLVED')
        elif status_param:
            # Generalized (2026-08-27, "Historique" tab, docs/deviations.md — Feature 5) so
            # `?status=RESOLVED` works for the history view, same as `?resolved=true` already
            # did on UnusualCaseListCreateView below — `OPEN` keeps its own special-cased
            # "exclude RESOLVED" meaning since `status` is otherwise free-text (see model
            # docstring), not a literal status value itself.
            qs = qs.filter(status=status_param)
        house_code = self.request.query_params.get('house_code')
        if house_code:
            qs = qs.filter(house_id=house_code)
        return qs


class EquipmentFaultResolveView(APIView):
    """POST /api/equipment-faults/{faultCode}/resolve/ — marks a fault resolved (2026-08-26,
    "Cas signalés", docs/deviations.md Part 16, Part D): sets `status='RESOLVED'` and stamps
    `repaired_date`/`resolved_by` (2026-08-27, "Historique" tab). Reserved to Technician/Admin,
    the same role set allowed to declare a fault in the first place — finally gives the cahier
    des charges section 8 "Valider une tâche de maintenance" permission-matrix row an actual
    endpoint (see model docstring). Deliberately left at Technician/Admin rather than narrowed to
    Admin/Farm Manager like `UnusualCaseResolveView` below — see docs/deviations.md ("Feature 5")
    for why the two resolve permissions differ."""

    permission_classes = [IsAdminOrTechnician]

    def post(self, request, fault_code):
        fault = get_object_or_404(EquipmentFault, fault_code=fault_code, house__farm=request.user.farm)
        fault.status = 'RESOLVED'
        fault.repaired_date = timezone.localdate()
        fault.resolved_by = request.user
        fault.save(update_fields=['status', 'repaired_date', 'resolved_by'])
        record_audit_log(request.user, 'equipment_fault.resolved', f'{fault.fault_code} — {fault.house.name}')
        return Response(EquipmentFaultSerializer(fault).data)


class UnusualCaseListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/unusual-cases/ — list/report unusual observations on a batch.
    Open to any authenticated user of the farm for both listing and creation (no role
    restriction is applied here, unlike most other write endpoints). `?resolved=false`
    (2026-08-26, "Cas signalés") excludes resolved cases; `?house_code=` scopes to one house."""

    serializer_class = UnusualCaseSerializer

    def get_queryset(self):
        qs = UnusualCase.objects.filter(batch__house__farm=self.request.user.farm).select_related(
            'batch__house', 'farmer', 'worker', 'resolved_by',
        )
        resolved_param = self.request.query_params.get('resolved')
        if resolved_param is not None:
            qs = qs.filter(resolved=resolved_param.lower() == 'true')
        house_code = self.request.query_params.get('house_code')
        if house_code:
            qs = qs.filter(batch__house_id=house_code)
        return qs


class UnusualCaseResolveView(APIView):
    """POST /api/unusual-cases/{caseCode}/resolve/ — marks a case resolved (2026-08-26, "Cas
    signalés", docs/deviations.md Part 16, Part D). Reserved to Admin/Farm Manager
    (`IsAdminOrFarmManager` — narrowed 2026-08-27, "Feature 5", from `IsAdminOrFarmManagerOrFarmer`:
    the Farmer responsible for a batch can report a case on it, same as anyone else, but no
    longer gets to also be the one who marks it resolved) — deliberately narrower than who can
    *report* a case (any authenticated farm user, including Worker and Farmer): marking a
    health/safety observation as handled is a judgment call for Admin/Farm Manager, structurally
    never the reporter themselves for the Farmer/Worker roles this observation type is mostly
    filed by."""

    permission_classes = [IsAdminOrFarmManager]

    def post(self, request, case_code):
        case = get_object_or_404(UnusualCase, case_code=case_code, batch__house__farm=request.user.farm)
        case.resolved = True
        case.resolved_at = timezone.now()
        case.resolved_by = request.user
        case.save(update_fields=['resolved', 'resolved_at', 'resolved_by'])
        record_audit_log(request.user, 'unusual_case.resolved', f'{case.case_code} — {case.batch.name or case.batch.batch_code}')
        return Response(UnusualCaseSerializer(case).data)
