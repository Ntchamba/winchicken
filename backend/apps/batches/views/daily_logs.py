from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.batches.models import PoultryBatch
from apps.batches.serializers import DailyLogSerializer
from apps.batches.services import record_quick_entry
from apps.core.permissions import IsAdminOrFarmManagerOrFarmerOrWorker


class DailyLogListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/batches/{batchCode}/daily-logs/ — daily mortality/feed/water/weight entry.
    Creation open to Farmer/Worker/Admin/Farm Manager (2026-08-27 bugfix — Admin was wrongly
    excluded by an over-narrow `IsFarmerOrWorker` check, see docs/deviations.md); one row per
    (batch, log_date).
    `PoultryBatch.current_count` (2026-08-25: computed from `initial_count` minus the sum of all
    `DailyLog.mortality` for the batch — see that model's `current_count` property) reflects a
    newly-created row automatically on its next read; nothing needs writing here anymore."""

    serializer_class = DailyLogSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminOrFarmManagerOrFarmerOrWorker()]
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
        serializer.save(batch=self.get_batch())


class DailyLogQuickEntryView(APIView):
    """PUT /api/batches/{batchCode}/daily-logs/quick-entry/ — the global/per-house dashboard's
    light quick-entry panel: mortality, eggsCollected, and (2026-08-25) avgSampleWeight for one
    batch and date, upserting the day's DailyLog row instead of erroring on a duplicate like the
    plain POST /daily-logs/ endpoint would (that one is a strict create, one row per (batch,
    log_date) — the two views are complementary, not a replacement for each other). Each of the
    three fields is independently optional in the request — an omitted field is left untouched
    on an existing row (never blanked to 0/null), so a weighing logged on a day that already has
    a mortality entry doesn't erase it, and vice versa; `feed_consumed_kg`/`water_consumed_l`/
    `notes` (not handled by this panel at all) are always left alone regardless.

    Permission matches the plain daily-log endpoint (Farmer/Worker/Admin/Farm Manager). The upsert-with-delta and
    cumulative-mortality logic live in apps.batches.services.record_quick_entry — this view only
    parses the request (distinguishing "field absent" from "field is 0", which `dict.get(...,
    default)` alone can't do) and turns the service's result into the right HTTP response.
    """

    permission_classes = [IsAdminOrFarmManagerOrFarmerOrWorker]

    def put(self, request, batch_code):
        batch = get_object_or_404(PoultryBatch, batch_code=batch_code, house__farm=request.user.farm)
        log_date = request.data.get('date')
        if not log_date:
            return Response({'detail': 'date est requis.'}, status=status.HTTP_400_BAD_REQUEST)

        raw_mortality = request.data.get('mortality')
        mortality = int(raw_mortality) if raw_mortality is not None else None
        eggs_collected = request.data.get('eggsCollected')
        raw_weight = request.data.get('avgSampleWeight')
        avg_sample_weight = float(raw_weight) if raw_weight is not None else None

        log, cumulative_pct, reference_range, error = record_quick_entry(
            batch, log_date, mortality=mortality, eggs_collected=eggs_collected, avg_sample_weight=avg_sample_weight
        )
        if error:
            return Response({'detail': error}, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            **DailyLogSerializer(log).data,
            'cumulativeMortalityPct': cumulative_pct,
            'mortalityReferenceRange': reference_range,
        })
