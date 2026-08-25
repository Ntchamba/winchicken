from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.batches.calculations import build_closing_report, weekly_kpi
from apps.batches.models import BatchStatus, PoultryBatch
from apps.batches.serializers import BatchClosingReportSerializer, DailyLogSerializer, PoultryBatchSerializer
from apps.core.permissions import IsAdminOrFarmManager


class PoultryBatchListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/batches/ — list/create batches for the farm, filterable by ?house_code=.
    Creation reserved to Admin / Farm Manager (section 8); rejected if the target house already
    has an ACTIVE batch (see `PoultryBatchSerializer.validate_house_code`)."""

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
        return qs


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
            batch.actual_end_date = timezone.now().date()
            batch.save()
            report = build_closing_report(batch)
        return Response(BatchClosingReportSerializer(report).data)


class DailyLogListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/batches/{batchCode}/daily-logs/ — daily mortality/feed/water/weight entry.
    Creation reserved to Farmer / Worker (section 8); one row per (batch, log_date). On create,
    decrements the batch's `current_count` by the logged `mortality`."""

    serializer_class = DailyLogSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            from apps.core.permissions import IsFarmerOrWorker
            return [IsFarmerOrWorker()]
        return [IsAuthenticated()]

    def get_batch(self):
        return get_object_or_404(
            PoultryBatch, batch_code=self.kwargs['batch_code'], house__farm=self.request.user.farm
        )

    def get_queryset(self):
        return self.get_batch().daily_logs.all()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['batch'] = self.get_batch()
        return context

    def perform_create(self, serializer):
        batch = self.get_batch()
        log = serializer.save(batch=batch)
        batch.current_count = max(0, batch.current_count - log.mortality)
        batch.save(update_fields=['current_count'])


@extend_schema(
    responses=inline_serializer(
        'WeeklyKpiResponse',
        {
            'batchCode': serializers.CharField(),
            'weeks': inline_serializer('WeeklyKpiWeek', {
                'week': serializers.IntegerField(),
                'mortalityPct': serializers.FloatField(),
                'feedConversionRatio': serializers.FloatField(allow_null=True),
                'avgWeightKg': serializers.FloatField(allow_null=True),
            }, many=True),
            'referenceRange': inline_serializer('WeeklyKpiReferenceRange', {
                'feedConversionRatio': serializers.ListField(child=serializers.FloatField()),
                'mortalityPct': serializers.ListField(child=serializers.FloatField()),
            }),
        },
    ),
    examples=[OpenApiExample(
        'Weekly KPI', value={
            'batchCode': 'BATCH-2026-014',
            'weeks': [
                {'week': 1, 'mortalityPct': 0.4, 'feedConversionRatio': 0.92, 'avgWeightKg': 0.18},
                {'week': 2, 'mortalityPct': 0.6, 'feedConversionRatio': 1.35, 'avgWeightKg': 0.42},
            ],
            'referenceRange': {'feedConversionRatio': [2.10, 2.30], 'mortalityPct': [3, 5]},
        },
        response_only=True,
    )],
)
class WeeklyKpiView(APIView):
    """GET /api/batches/{batchCode}/kpi/weekly/ — per-week mortality/FCR/avg-weight series for
    the house-detail page chart, plus the static favorable/unfavorable reference bands
    (implementation-detail spec 11.1). See apps.batches.calculations.weekly_kpi for the formulas."""

    permission_classes = [IsAuthenticated]

    def get(self, request, batch_code):
        batch = get_object_or_404(PoultryBatch, batch_code=batch_code, house__farm=request.user.farm)
        return Response(weekly_kpi(batch))
