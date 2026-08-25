from rest_framework import serializers

from apps.batches.models import BatchClosingReport, BatchStatus, DailyLog, PoultryBatch


def generate_batch_code(farm_id):
    """Builds the next `BATCH-{year}-{seq}` code, scoped per farm and per calendar year
    (counts existing rows for that farm+year prefix rather than a persisted counter)."""
    from django.utils import timezone
    year = timezone.now().year
    count = PoultryBatch.objects.filter(house__farm_id=farm_id, batch_code__startswith=f'BATCH-{year}-').count() + 1
    return f'BATCH-{year}-{count:03d}'


class PoultryBatchSerializer(serializers.ModelSerializer):
    """GET/POST payload for /api/batches/. `batch_code` and `current_count` are always
    server-generated/server-managed — `current_count` starts equal to `initial_count` and is
    only ever decremented by DailyLog creation (see DailyLogListCreateView.perform_create)."""

    house_code = serializers.CharField(source='house_id', help_text='PoultryHouse.house_code this batch is hosted in.')

    class Meta:
        model = PoultryBatch
        fields = [
            'batch_code', 'name', 'house_code', 'farmer', 'production_type', 'breed', 'initial_count',
            'current_count', 'start_date', 'planned_end_date', 'actual_end_date', 'status', 'created_at',
        ]
        read_only_fields = ['batch_code', 'current_count', 'actual_end_date', 'status', 'created_at']
        extra_kwargs = {
            'initial_count': {'help_text': 'Number of chicks placed at batch start.'},
        }

    def validate_house_code(self, value):
        if PoultryBatch.objects.filter(house_id=value, status=BatchStatus.ACTIVE).exists():
            raise serializers.ValidationError("Ce bâtiment a déjà une bande active (vide sanitaire requis).")
        return value

    def create(self, validated_data):
        farm = self.context['request'].user.farm
        validated_data['batch_code'] = generate_batch_code(farm.id)
        validated_data['current_count'] = validated_data['initial_count']
        return super().create(validated_data)


class DailyLogSerializer(serializers.ModelSerializer):
    """POST payload for /api/batches/{batchCode}/daily-logs/ — one row per (batch, log_date).
    `mortality` cannot exceed the batch's *current* count (validated here); on save, the view
    decrements `PoultryBatch.current_count` by `mortality` (never below 0)."""

    class Meta:
        model = DailyLog
        fields = ['id', 'log_date', 'mortality', 'feed_consumed_kg', 'water_consumed_l', 'avg_sample_weight', 'notes']
        read_only_fields = ['id']
        extra_kwargs = {
            'avg_sample_weight': {'help_text': 'Average sample weight in kg, if birds were weighed that day; feeds the FCR calculation.'},
        }

    def validate(self, attrs):
        batch = self.context['batch']
        mortality = attrs.get('mortality', 0)
        if mortality > batch.current_count:
            raise serializers.ValidationError({'mortality': "Ne peut pas dépasser l'effectif actuel de la bande."})
        return attrs


class BatchClosingReportSerializer(serializers.ModelSerializer):
    """Response shape of PATCH /api/batches/{batchCode}/close/ (implementation-detail spec 11.4)
    — every figure is computed by apps.batches.calculations.build_closing_report, never entered
    manually."""

    class Meta:
        model = BatchClosingReport
        fields = [
            'batch', 'closing_date', 'total_mortality_pct', 'feed_conversion_ratio',
            'revenue', 'total_variable_cost', 'unit_cost_price', 'total_margin',
        ]
