from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.batches.calculations import build_closing_report
from apps.batches.models import BatchStatus, PoultryBatch
from apps.batches.serializers import BatchClosingReportSerializer, PoultryBatchQuickEditSerializer, PoultryBatchSerializer
from apps.batches.services import finalize_new_batch, sync_weighing_reminder
from apps.core.permissions import CanEditHouseProtocol, IsAdminOrFarmManager
from apps.core.services import record_audit_log


class PoultryBatchListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/batches/ — list/create batches for the farm, filterable by ?house_code= and
    ?status=. Farm-wide callers that want each house's current batch ask for ?status=ACTIVE: the
    unfiltered list is paginated newest-first, and a long-running layer flock falls off page 1.
    Creation reserved to Admin / Farm Manager (section 8); rejected if the target house already
    has an ACTIVE batch (see `PoultryBatchSerializer.validate_house_code`).

    On create, also expands the house's current protocol into PROTOCOL_TASK AlertRule rows for
    this batch (apps.batches.services.finalize_new_batch) — the same call OnboardingView makes
    when a batch is created there; this is the "add a further batch to an already-protocoled
    house" path (a house's second, third, ... batch), added 2026-08-25.
    """

    serializer_class = PoultryBatchSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminOrFarmManager()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = PoultryBatch.objects.filter(house__farm=self.request.user.farm)
        house_code = self.request.query_params.get('house_code')
        if house_code:
            qs = qs.filter(house_id=house_code)
        status_filter = self.request.query_params.get('status')
        if status_filter:
            if status_filter not in BatchStatus.values:
                raise serializers.ValidationError({'status': f'Statut inconnu : {status_filter}.'})
            qs = qs.filter(status=status_filter)
        return qs

    def perform_create(self, serializer):
        with transaction.atomic():
            batch = serializer.save()
            finalize_new_batch(batch)
        record_audit_log(self.request.user, 'batch.created', f'Bande {batch.name or batch.batch_code}')


class PoultryBatchDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET/PATCH/DELETE /api/batches/{batchCode}/ — added 2026-08-25 alongside the "Modifier"
    protocol modal: `PoultryBatch.name` had a form field and a model column since an earlier
    task, but no endpoint ever persisted it outside of batch *creation* — editing an existing
    batch's name silently went nowhere. PATCH is scoped to `name`/`weighing_frequency` only (see
    `PoultryBatchQuickEditSerializer`) and touches only this `PoultryBatch` row — never
    `PoultryHouse`, on purpose (see that serializer's docstring and docs/deviations.md for the
    bug this closes). A `weighing_frequency` change re-syncs the batch's `WEIGHING_REMINDER`
    `AlertRule` (apps.batches.services.sync_weighing_reminder) in the same request.

    DELETE (2026-08-25, "batch deletion" task) is a permanent, cascading delete — every
    `DailyLog`/`Alert`/`AlertRule`/`UnusualCase`/`Vaccination`/`StockMovement`/`Expense`/`Sale`/
    `BatchClosingReport` row tied to this batch goes with it (all `on_delete=CASCADE` on their
    `batch` FK — see each model). Reserved to Admin/Farm Manager, same as creating a batch —
    stricter than the PATCH permission (any role that can edit the protocol), since deleting is
    materially more destructive and irreversible than renaming.
    """

    lookup_field = 'batch_code'

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'PUT'):
            return PoultryBatchQuickEditSerializer
        return PoultryBatchSerializer

    def get_permissions(self):
        if self.request.method in ('PATCH', 'PUT'):
            return [CanEditHouseProtocol()]
        if self.request.method == 'DELETE':
            return [IsAdminOrFarmManager()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return PoultryBatch.objects.filter(house__farm=self.request.user.farm)

    def perform_update(self, serializer):
        with transaction.atomic():
            batch = serializer.save()
            sync_weighing_reminder(batch)
        record_audit_log(self.request.user, 'batch.updated', f'Bande {batch.name or batch.batch_code}')

    def perform_destroy(self, instance):
        record_audit_log(self.request.user, 'batch.deleted', f'Bande {instance.name or instance.batch_code}')
        instance.delete()


@extend_schema(
    request=None,
    responses={200: BatchClosingReportSerializer, 400: inline_serializer('BatchAlreadyClosed', {'detail': serializers.CharField()})},
)
class BatchCloseView(APIView):
    """PATCH /api/batches/{batchCode}/close/ — closes the batch (status -> CLOSED, sets
    actual_end_date to today) and computes+persists its BatchClosingReport in the same
    transaction. Reserved to Admin / Farm Manager (section 8). Returns 400 if the batch is
    already closed — closing is a one-way, non-idempotent action from the API's point of view."""

    permission_classes = [IsAdminOrFarmManager]

    def patch(self, request, batch_code):
        batch = get_object_or_404(PoultryBatch, batch_code=batch_code, house__farm=request.user.farm)
        if batch.status == BatchStatus.CLOSED:
            return Response({'detail': 'Cette bande est déjà clôturée.'}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            from django.utils import timezone
            batch.status = BatchStatus.CLOSED
            batch.actual_end_date = timezone.localdate()
            batch.save()
            report = build_closing_report(batch)
        record_audit_log(request.user, 'batch.closed', f'Bande {batch.name or batch.batch_code}')
        return Response(BatchClosingReportSerializer(report).data)
