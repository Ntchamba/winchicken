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
    `current_count` starts equal to `initial_count` and is decremented by
    `DailyLogListCreateView.perform_create` each time a DailyLog with mortality > 0 is logged.
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
    current_count = models.PositiveIntegerField()
    start_date = models.DateField()
    planned_end_date = models.DateField(null=True, blank=True)
    actual_end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=8, choices=BatchStatus.choices, default=BatchStatus.ACTIVE)
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
