from rest_framework import serializers

from apps.batches.models import BatchClosingReport, BatchStatus, DailyLog, PoultryBatch


def validate_batch_name(value):
    """`PoultryBatch.name` is `blank=True` at the model level (legacy rows / non-form paths),
    but every real batch-creation flow requires it — reject empty or whitespace-only."""
    if not value or not value.strip():
        raise serializers.ValidationError("Le nom de la bande est requis.")
    return value.strip()


def generate_batch_code(farm_id):
    """Builds the next `BATCH-{year}-{seq}` code, scoped per farm and per calendar year
    (counts existing rows for that farm+year prefix rather than a persisted counter)."""
    from django.utils import timezone
    year = timezone.now().year
    count = PoultryBatch.objects.filter(house__farm_id=farm_id, batch_code__startswith=f'BATCH-{year}-').count() + 1
    return f'BATCH-{year}-{count:03d}'


class PoultryBatchSerializer(serializers.ModelSerializer):
    """GET/POST payload for /api/batches/. `batch_code` is server-generated. `current_count`
    (2026-08-25) is a computed `@property` on the model, not a stored field — DRF auto-detects
    it via `build_property_field` and serializes it read-only with no extra work here; see the
    model's docstring for why it's computed rather than stored."""

    house_code = serializers.CharField(source='house_id', help_text='PoultryHouse.house_code this batch is hosted in.')

    class Meta:
        model = PoultryBatch
        fields = [
            'batch_code', 'name', 'house_code', 'farmer', 'production_type', 'breed', 'initial_count',
            'current_count', 'start_date', 'planned_end_date', 'actual_end_date', 'status',
            'weighing_frequency', 'created_at',
        ]
        read_only_fields = ['batch_code', 'current_count', 'actual_end_date', 'status', 'created_at']
        extra_kwargs = {
            'name': {'required': True, 'allow_blank': False},
            'initial_count': {'help_text': 'Number of chicks placed at batch start.'},
            'weighing_frequency': {'help_text': 'Optional "Fréquence de pesée" — DAY | WEEK | MONTH | null. See PoultryBatch model docstring.'},
        }

    validate_name = staticmethod(validate_batch_name)

    def validate_house_code(self, value):
        if PoultryBatch.objects.filter(house_id=value, status=BatchStatus.ACTIVE).exists():
            raise serializers.ValidationError("Ce bâtiment a déjà une bande active (vide sanitaire requis).")
        return value

    def create(self, validated_data):
        farm = self.context['request'].user.farm
        validated_data['batch_code'] = generate_batch_code(farm.id)
        return super().create(validated_data)


class PoultryBatchQuickEditSerializer(serializers.ModelSerializer):
    """PATCH payload for /api/batches/{batchCode}/ — `name` and (2026-08-25) `weighing_frequency`
    only; named for what it covers, not just "name" anymore. Deliberately not the full
    `PoultryBatchSerializer` reused here: this endpoint exists for the few fields the "Modifier"
    protocol-edit modal can change on an already-created batch, and should not become a
    general-purpose batch editor by accident — `house`/`status`/`production_type`/etc. all stay
    read-only/unreachable through this view no matter what a client sends."""

    class Meta:
        model = PoultryBatch
        fields = ['batch_code', 'name', 'weighing_frequency']
        read_only_fields = ['batch_code']
        extra_kwargs = {'name': {'required': False, 'allow_blank': False}}

    validate_name = staticmethod(validate_batch_name)


class DailyLogSerializer(serializers.ModelSerializer):
    """POST payload for /api/batches/{batchCode}/daily-logs/ — one row per (batch, log_date).
    `mortality` cannot exceed the batch's *current* count (validated here) — `current_count`
    (2026-08-25) is computed from this same DailyLog history, so saving a new row here is
    reflected in it automatically on the next read, with nothing further to write."""

    class Meta:
        model = DailyLog
        fields = ['id', 'log_date', 'mortality', 'feed_consumed_kg', 'water_consumed_l', 'avg_sample_weight', 'eggs_collected', 'notes']
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
