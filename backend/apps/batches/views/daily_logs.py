import datetime
import math

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
        qs = self.get_batch().daily_logs.all()
        # ?weighed=1 — "Pesées récentes": weighed days, newest first. The plain list is oldest
        # first and paginated by 20, so reading page 1 stopped at day 20 of the cycle.
        if self.request.query_params.get('weighed') == '1':
            qs = qs.filter(avg_sample_weight__isnull=False).order_by('-log_date')
        return qs

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['batch'] = self.get_batch()
        return context

    def perform_create(self, serializer):
        serializer.save(batch=self.get_batch())


class _Invalid(Exception):
    """A quick-entry field that cannot be stored; its message is the French 400 detail."""


def _parse_count(raw, message):
    """A whole number >= 0 (JSON number or numeric string), None when absent."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise _Invalid(message)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise _Invalid(message)
    if not math.isfinite(value) or value < 0 or value != int(value):
        raise _Invalid(message)
    return int(value)


def _parse_weight(raw):
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise _Invalid("Le poids moyen doit être un nombre de kilos supérieur à 0.")
    if isinstance(raw, bool) or not math.isfinite(value) or not value > 0:
        raise _Invalid("Le poids moyen doit être un nombre de kilos supérieur à 0.")
    return value


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
        raw_date = request.data.get('date')
        if not raw_date:
            return Response({'detail': 'La date est requise.'}, status=status.HTTP_400_BAD_REQUEST)
        # Parsed here, not left to the ORM: an impossible date, a word in a number field or a
        # negative count used to reach the database and come back as a 500.
        try:
            log_date = datetime.date.fromisoformat(str(raw_date))
        except ValueError:
            return Response({'detail': "La date n'est pas valide (format AAAA-MM-JJ)."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            mortality = _parse_count(request.data.get('mortality'), "La mortalité doit être un nombre entier positif ou nul.")
            eggs_collected = _parse_count(request.data.get('eggsCollected'), "Le nombre d'œufs doit être un nombre entier positif ou nul.")
            avg_sample_weight = _parse_weight(request.data.get('avgSampleWeight'))
        except _Invalid as invalid:
            return Response({'detail': str(invalid)}, status=status.HTTP_400_BAD_REQUEST)

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
