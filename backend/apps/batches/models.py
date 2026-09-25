from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.houses.models import PoultryHouse


class ProductionType(models.TextChoices):
    BROILER = 'BROILER', 'Broiler'
    PULLET = 'PULLET', 'Pullet'
    LAYER = 'LAYER', 'Layer'


class BatchStatus(models.TextChoices):
    """A house is in "sanitary void" (empty, between flocks) exactly when it has no batch with
    status=ACTIVE — the frontend derives that state itself rather than reading a stored flag."""

    ACTIVE = 'ACTIVE', 'Active'
    CLOSED = 'CLOSED', 'Closed'


class PoultryBatch(models.Model):
    """A single batch (flock) of birds raised together in one house.

    Only one ACTIVE batch per house at a time — enforced at the database level by the
    `one_active_batch_per_house` partial UniqueConstraint below (single-batch / sanitary-void
    principle: a house must be fully vacated and closed before a new batch can start there).
    `batch_code` is server-generated (`BATCH-{year}-{seq}`, see
    apps.batches.serializers.generate_batch_code) — no form collects it manually.

    `current_count` (2026-08-25) is a computed property, not a stored column — see the property
    below. It used to be a `PositiveIntegerField`, set to `initial_count` at creation and
    decremented by hand in `DailyLogListCreateView.perform_create` / `apps.batches.services.
    record_quick_entry` each time mortality was logged. That worked for both of this project's
    own write paths (including the delta-correction case — editing an already-logged day's
    mortality up or down) but had one real gap: the Django admin (`/admin/batches/dailylog/`)
    edits `DailyLog` rows directly, calling `.save()` with no knowledge of either code path, so
    a mortality correction made there silently left `current_count` stale. Computing it fresh
    from `initial_count - SUM(daily_logs.mortality)` on every read eliminates that whole class
    of drift instead of chasing every possible write path with a signal — see docs/deviations.md
    for the audit that found this and the fields it's used from (FCR/unit-cost calculations, the
    quick-entry endpoint's own over-mortality validation, `VaccinationSerializer`'s dose check).
    """

    batch_code = models.CharField(max_length=32, primary_key=True)
    name = models.CharField(
        max_length=255, blank=True,
        help_text='Human-friendly name (e.g. "Bande printemps 2026") — required by the protocol '
                   'form when starting a batch, but blank=True at the model level so existing '
                   'rows from before this field (none in this project\'s history) and any other '
                   'creation path stay valid without a forced default.',
    )
    house = models.ForeignKey(PoultryHouse, on_delete=models.CASCADE, related_name='batches')
    farmer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_batches'
    )
    production_type = models.CharField(max_length=16, choices=ProductionType.choices)
    breed = models.CharField(max_length=255, blank=True)
    initial_count = models.PositiveIntegerField()
    start_date = models.DateField()
    planned_end_date = models.DateField(null=True, blank=True)
    actual_end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=8, choices=BatchStatus.choices, default=BatchStatus.ACTIVE)
    weighing_frequency = models.CharField(
        max_length=8, choices=[('DAY', 'Day'), ('WEEK', 'Week'), ('MONTH', 'Month')], null=True, blank=True,
        help_text='Optional "Fréquence de pesée" (2026-08-25) — reuses apps.protocols.models.'
                   'ProtocolUnit\'s three values by string (not a direct FK/import, to avoid a '
                   'protocols->batches model dependency) rather than defining a near-duplicate '
                   'enum. Drives a recurring WEIGHING_REMINDER AlertRule '
                   '(apps.batches.services.sync_weighing_reminder) and the "tâches à effectuer '
                   'maintenant" panel — never restricts when a weight can actually be logged '
                   'through the quick-entry panel, which accepts a weight on any date regardless.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date']
        constraints = [
            models.UniqueConstraint(
                fields=['house'],
                condition=Q(status='ACTIVE'),
                name='one_active_batch_per_house',
            )
        ]

    def __str__(self):
        return self.batch_code

    @property
    def current_count(self):
        """`initial_count` minus the sum of every logged `DailyLog.mortality` for this batch —
        computed fresh on every access rather than stored (see class docstring). Clamped at 0,
        matching the old stored field's `max(0, ...)` guard in its write paths, even though a
        correctly-behaving app should never actually reach a negative raw total.

        The sum is read from wherever it is already at hand, so a list of batches does not cost
        one aggregate query each: the `total_mortality` annotation that
        `apps.batches.services.with_current_count` adds, else prefetched `daily_logs`, else one
        aggregate query. All three are the same SUM over the same rows."""
        total_mortality = getattr(self, 'total_mortality', None)
        if total_mortality is None:
            prefetched = getattr(self, '_prefetched_objects_cache', {}).get('daily_logs')
            if prefetched is not None:
                total_mortality = sum(log.mortality for log in prefetched)
            else:
                from django.db.models import Sum
                total_mortality = self.daily_logs.aggregate(total=Sum('mortality'))['total'] or 0
        return max(0, self.initial_count - total_mortality)


class DailyLog(models.Model):
    """One record per day and per batch (unique together, see `one_daily_log_per_batch_per_day`
    below). Feeds every livestock KPI in apps.batches.calculations (mortality_pct, FCR,
    weekly_kpi) and triggers `apps.alerts.services.check_consumption_deviation` on creation via
    the `on_daily_log_saved` signal when the water/feed ratio falls outside 1.6-2.2."""

    batch = models.ForeignKey(PoultryBatch, on_delete=models.CASCADE, related_name='daily_logs')
    log_date = models.DateField()
    mortality = models.PositiveIntegerField(default=0)
    feed_consumed_kg = models.FloatField(default=0)
    water_consumed_l = models.FloatField(default=0)
    avg_sample_weight = models.FloatField(null=True, blank=True)
    eggs_collected = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Eggs collected that day, farm-wide quick-entry field (2026-08-25). Nullable '
                   'since most batches are broilers with no laying to record; a dedicated '
                   'laying-rate chart is deferred to a later iteration — this field only '
                   'captures the raw data point for now.',
    )
    notes = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['log_date']
        constraints = [
            models.UniqueConstraint(fields=['batch', 'log_date'], name='one_daily_log_per_batch_per_day')
        ]

    def __str__(self):
        return f'{self.batch_id} · {self.log_date}'


class BatchClosingReport(models.Model):
    """Snapshot computed by `apps.batches.calculations.build_closing_report` at batch closing
    (PATCH /api/batches/{batchCode}/close/) — profit is never entered manually, always derived
    from the batch's real Expense/Sale rows at that point in time. `update_or_create`d, so
    closing an already-closed batch would recompute rather than duplicate (the view itself
    rejects a second close with 400 before that can happen)."""

    batch = models.OneToOneField(PoultryBatch, on_delete=models.CASCADE, primary_key=True, related_name='closing_report')
    closing_date = models.DateField(auto_now_add=True)
    total_mortality_pct = models.FloatField()
    feed_conversion_ratio = models.FloatField(null=True)
    revenue = models.DecimalField(max_digits=14, decimal_places=2)
    total_variable_cost = models.DecimalField(max_digits=14, decimal_places=2)
    unit_cost_price = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    total_margin = models.DecimalField(max_digits=14, decimal_places=2)

    def __str__(self):
        return f'Closing report · {self.batch_id}'
