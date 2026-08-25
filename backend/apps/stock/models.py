from django.db import models

from apps.batches.models import PoultryBatch
from apps.core.models import Farm


class ItemCategory(models.TextChoices):
    FEED = 'FEED', 'Feed'
    VETERINARY = 'VETERINARY', 'Veterinary'
    EQUIPMENT = 'EQUIPMENT', 'Equipment'
    BEDDING = 'BEDDING', 'Bedding'


class FeedStage(models.TextChoices):
    STARTER = 'STARTER', 'Starter'
    GROWER = 'GROWER', 'Grower'
    FINISHER = 'FINISHER', 'Finisher'
    PULLET_STAGE = 'PULLET_STAGE', 'Pullet stage'
    LAYER_STAGE = 'LAYER_STAGE', 'Layer stage'
    NOT_APPLICABLE = 'NOT_APPLICABLE', 'Not applicable'


class StockItem(models.Model):
    """A tracked warehouse item definition (feed/vet/equipment/bedding) — not a stock level by
    itself. `item_code` is server-generated (`{CAT3}-{farmId}-{seq}`, see
    apps.stock.serializers.generate_item_code) — no form collects it manually. Current on-hand
    quantity is never stored on this row; it is computed on demand from StockMovement rows by
    `apps.stock.calculations.current_quantity` and crossing below `alert_threshold` fires a
    LOW_STOCK Alert (see apps.alerts.services.check_low_stock, triggered by a post_save signal
    on StockMovement)."""

    item_code = models.CharField(max_length=32, primary_key=True)
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='stock_items')
    category = models.CharField(max_length=16, choices=ItemCategory.choices)
    name = models.CharField(max_length=255)
    unit = models.CharField(max_length=16)
    feed_stage = models.CharField(max_length=16, choices=FeedStage.choices, default=FeedStage.NOT_APPLICABLE)
    cold_chain_required = models.BooleanField(default=False)
    alert_threshold = models.FloatField(default=0)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return self.name


class MovementType(models.TextChoices):
    """IN = restocking (manual entry or a received PurchaseOrder, see
    apps.finance.serializers.PurchaseOrderSerializer.update); OUT = consumption/usage."""

    IN = 'IN', 'In'
    OUT = 'OUT', 'Out'


class StockMovement(models.Model):
    """One inventory transaction for a StockItem. `current_quantity(item)` is
    `SUM(quantity WHERE movement_type=IN) - SUM(quantity WHERE movement_type=OUT)` computed at
    read time (apps.stock.calculations.current_quantity) — never cached on StockItem. Saving one
    triggers a LOW_STOCK check for its item via the `on_stock_movement_saved` signal."""

    item = models.ForeignKey(StockItem, on_delete=models.CASCADE, related_name='movements')
    batch = models.ForeignKey(PoultryBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_movements')
    movement_type = models.CharField(max_length=4, choices=MovementType.choices)
    quantity = models.FloatField()
    movement_date = models.DateField()
    supplier_batch_number = models.CharField(max_length=100, blank=True)
    supplier = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-movement_date', '-id']

    def __str__(self):
        return f'{self.item_id} · {self.movement_type} · {self.quantity}'


class Vaccination(models.Model):
    """One vaccination event for a batch, using a StockItem of category VETERINARY.

    `doses_used` must be >= `batch.current_count` — enforced in
    `apps.stock.serializers.VaccinationSerializer.validate` (application-level, not a DB
    CheckConstraint), reflecting that a reconstituted vial is used for the whole flock, not
    partially. `reconstitution_time + 2h` is the strict expiry window once mixed (documented
    convention — not itself enforced anywhere in code as a constraint or alert)."""

    batch = models.ForeignKey(PoultryBatch, on_delete=models.CASCADE, related_name='vaccinations')
    item = models.ForeignKey(StockItem, on_delete=models.CASCADE, related_name='vaccinations')
    scheduled_date = models.DateField(null=True, blank=True)
    administered_date = models.DateField(null=True, blank=True)
    reconstitution_time = models.DateTimeField(null=True, blank=True)
    doses_used = models.PositiveIntegerField()
    status = models.CharField(max_length=32, default='SCHEDULED')

    class Meta:
        ordering = ['-scheduled_date']

    def __str__(self):
        return f'{self.batch_id} · {self.item_id}'
