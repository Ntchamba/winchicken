from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.batches.calculations import farm_health_score, growth_curve, weekly_kpi
from apps.batches.models import BatchStatus, PoultryBatch


@extend_schema(
    responses=inline_serializer(
        'GrowthCurvesResponse',
        {
            'batchCode': serializers.CharField(),
            'batchName': serializers.CharField(),
            'houseCode': serializers.CharField(),
            'houseName': serializers.CharField(),
            'points': inline_serializer('GrowthCurvePoint', {
                'dayOfCycle': serializers.IntegerField(),
                'weightKg': serializers.FloatField(allow_null=True),
                'survivalPct': serializers.FloatField(allow_null=True),
            }, many=True),
        },
        many=True,
    ),
)
class GrowthCurvesView(APIView):
    """GET /api/batches/growth-curves/ — day-of-cycle weight + survival series for the global
    view's overlaid, multi-batch chart (2026-08-25). Defaults to every ACTIVE batch on the farm;
    `?batch_code=` or `?house_code=` narrows to one batch (the house-detail view's single-line
    scope) — same endpoint for both, per apps.batches.calculations.growth_curve."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = PoultryBatch.objects.filter(house__farm=request.user.farm, status=BatchStatus.ACTIVE)
        batch_code = request.query_params.get('batch_code')
        house_code = request.query_params.get('house_code')
        if batch_code:
            qs = qs.filter(batch_code=batch_code)
        if house_code:
            qs = qs.filter(house_id=house_code)

        results = [
            {
                'batchCode': batch.batch_code,
                'batchName': batch.name,
                'houseCode': batch.house_id,
                'houseName': batch.house.name,
                'points': growth_curve(batch),
            }
            for batch in qs.select_related('house')
        ]
        return Response(results)


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


@extend_schema(
    responses=inline_serializer('FarmHealthScoreResponse', {
        'tier': serializers.ChoiceField(choices=['good', 'watch', 'critical']),
        'label': serializers.CharField(), 'reason': serializers.CharField(),
    }),
)
class FarmHealthScoreView(APIView):
    """GET /api/batches/health-score/ — the global view's farm health badge (2026-08-26,
    docs/deviations.md Part 16, Part A). See `apps.batches.calculations.farm_health_score` for
    the full, documented tier rule set."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(farm_health_score(request.user.farm))
