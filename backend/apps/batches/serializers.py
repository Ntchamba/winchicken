from rest_framework import serializers

from apps.batches.models import BatchClosingReport, BatchStatus, DailyLog, PoultryBatch


def validate_batch_name(value):
    """`PoultryBatch.name` is `blank=True` at the model level (legacy rows / non-form paths),
    but every real batch-creation flow requires it — reject empty or whitespace-only."""
    if not value or not value.strip():
        raise serializers.ValidationError("Le nom de la bande est requis.")
    return value.strip()


# How far a batch's dates may sit from today. A layer flock runs ~18 months, so a batch entered
# mid-cycle can have started well over a year ago; nobody places chicks years ahead, and no
# cycle outlives three years. Beyond these a date is a typo (1900, 2200), and it would make
# `day_of_cycle` read 46 289 or -63 284 on every screen.
BATCH_START_MAX_PAST_DAYS = 2 * 365
BATCH_START_MAX_FUTURE_DAYS = 365
BATCH_CYCLE_MAX_DAYS = 3 * 365


def batch_value_errors(*, initial_count, max_capacity, start_date, planned_end_date) -> dict:
    """The one set of plausibility rules for a new batch, shared by POST /api/batches/ and the
    onboarding endpoint (the UI's "+ Nouvelle bande"), so the two cannot drift apart. Returns
    `{field: message}` — empty when the batch is plausible. Field names are the model's."""
    from django.utils import timezone

    from apps.core.formatting import fr_number
    errors = {}
    if initial_count is not None:
        if initial_count < 1:
            errors['initial_count'] = "L'effectif de départ doit être d'au moins 1 volaille."
        elif max_capacity is not None and initial_count > max_capacity:
            errors['initial_count'] = (
                f"L'effectif de départ ({fr_number(initial_count)}) dépasse la capacité maximale "
                f"du bâtiment ({fr_number(max_capacity)})."
            )
    if start_date is not None:
        today = timezone.localdate()
        if (today - start_date).days > BATCH_START_MAX_PAST_DAYS:
            errors['start_date'] = "La date de début est trop ancienne (plus de 2 ans)."
        elif (start_date - today).days > BATCH_START_MAX_FUTURE_DAYS:
            errors['start_date'] = "La date de début est trop loin dans le futur (plus d'un an)."
        if planned_end_date is not None:
            if planned_end_date < start_date:
                errors['planned_end_date'] = "La date de fin prévue ne peut pas précéder la date de début."
            elif (planned_end_date - start_date).days > BATCH_CYCLE_MAX_DAYS:
                errors['planned_end_date'] = "Le cycle ne peut pas dépasser 3 ans."
    return errors


def generate_batch_code(farm_id):
    """Builds the next `BATCH-{year}-{seq}` code — one past the highest in use for the farm-local
    year (`localdate`: on 31 December after 23:00 Africa/Douala the UTC year is already the next).
    `batch_code` is the primary key across the whole table, so the sequence is too; `farm_id` is
    kept for the callers' signature. Never a row count — see apps.core.codes."""
    from django.utils import timezone

    from apps.core.codes import next_sequential_code
    year = timezone.localdate().year
    return next_sequential_code(PoultryBatch, 'batch_code', f'BATCH-{year}-')


class PoultryBatchSerializer(serializers.ModelSerializer):
    """GET/POST payload for /api/batches/. `batch_code` is server-generated. `current_count`
    (2026-08-25) is a computed `@property` on the model, not a stored field — DRF auto-detects
    it via `build_property_field` and serializes it read-only with no extra work here; see the
    model's docstring for why it's computed rather than stored."""

    house_code = serializers.CharField(source='house_id', help_text='PoultryHouse.house_code this batch is hosted in.')
    day_of_cycle = serializers.SerializerMethodField(
        help_text="Day of the cycle today, farm-local: 0 on the start date (apps.batches.services.day_of_cycle).",
    )

    def get_day_of_cycle(self, batch) -> int:
        from apps.batches.services import day_of_cycle
        return day_of_cycle(batch)

    class Meta:
        model = PoultryBatch
        fields = [
            'batch_code', 'name', 'house_code', 'farmer', 'production_type', 'breed', 'initial_count',
            'current_count', 'start_date', 'planned_end_date', 'actual_end_date', 'status',
            'weighing_frequency', 'created_at', 'day_of_cycle',
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

    def validate(self, attrs):
        from apps.houses.models import PoultryHouse

        house = PoultryHouse.objects.filter(
            house_code=attrs.get('house_id'), farm=self.context['request'].user.farm,
        ).first()
        if house is None:
            raise serializers.ValidationError({'house_code': "Bâtiment introuvable."})
        errors = batch_value_errors(
            initial_count=attrs.get('initial_count'), max_capacity=house.max_capacity,
            start_date=attrs.get('start_date'), planned_end_date=attrs.get('planned_end_date'),
        )
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data):
        from apps.core.codes import create_with_code
        farm = self.context['request'].user.farm

        def create():
            validated_data['batch_code'] = generate_batch_code(farm.id)
            return super(PoultryBatchSerializer, self).create(validated_data)
        return create_with_code(create)


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
        from apps.batches.services import validate_log_date

        batch = self.context['batch']
        # Same day rules as the quick entry (closed batch, future day, before the start).
        date_error = validate_log_date(batch, attrs['log_date']) if 'log_date' in attrs else None
        if date_error:
            raise serializers.ValidationError({'log_date': date_error})
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
