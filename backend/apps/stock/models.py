from django.db import models

from apps.batches.models import PoultryBatch
from apps.core.models import Farm


class ItemCategory(models.TextChoices):
    """Kept as a *kind* discriminator, not the category itself (2026-08-28 — custom stock
    categories). Since `StockItem.category` became an FK to `StockCategory`, this enum now lives
    on `StockCategory.kind`: the four defaults seeded per farm carry `FEED`/`VETERINARY`/
    `EQUIPMENT`/`BEDDING` so `StockItem.feed_stage` / `cold_chain_required` semantics and the
    finance breakdown mapping survive a category label rename; user-added categories are
    `CUSTOM`. Name unchanged so `apps.finance.calculations`'s existing import keeps working."""

    FEED = 'FEED', 'Feed'
    VETERINARY = 'VETERINARY', 'Veterinary'
    EQUIPMENT = 'EQUIPMENT', 'Equipment'
    BEDDING = 'BEDDING', 'Bedding'
    CUSTOM = 'CUSTOM', 'Custom'


# Mirrors apps.protocols.models.DEFAULT_PROTOCOL_CATEGORIES: the four categories seeded for
# every Farm (apps.stock.signals) — structural UI scaffolding, empty of items, so seeding them
# automatically doesn't violate the no-default-data rule. `icon` values are lucide-react icon
# component names, resolved on the frontend via a lookup map (fallback: Package).
DEFAULT_STOCK_CATEGORIES = [
    {'label': 'Aliment', 'icon': 'Wheat', 'kind': ItemCategory.FEED},
    {'label': 'Vétérinaire', 'icon': 'Stethoscope', 'kind': ItemCategory.VETERINARY},
    {'label': 'Équipement', 'icon': 'Wrench', 'kind': ItemCategory.EQUIPMENT},
    {'label': 'Litière', 'icon': 'Layers', 'kind': ItemCategory.BEDDING},
]

# Curated icon picker for custom stock categories — kept in sync by hand with
# frontend/src/components/StockParametersForm.jsx's STOCK_ICON_OPTIONS. The four defaults' own
# icons are always valid too.
STOCK_CATEGORY_ICON_CHOICES = [
    'Wheat', 'Stethoscope', 'Wrench', 'Layers', 'Package', 'Syringe', 'Droplets', 'Boxes',
    'ShoppingCart', 'Thermometer', 'Bug', 'ClipboardList', 'Egg', 'Wind',
]


class StockCategory(models.Model):
    """A stock parameter tab for one farm — the four defaults (Aliment/Vétérinaire/Équipement/
    Litière) plus any custom categories a user adds via
    POST /api/farms/{farmId}/stock-categories/. Same structure as
    `apps.protocols.models.ProtocolCategory`, plus a `kind` discriminator (see `ItemCategory`).

    Deleting a category cascades to delete its StockItem rows (`StockItem.category` is
    `on_delete=CASCADE`), mirroring how deleting a ProtocolCategory cascades to its
    ProtocolTemplate rows — the frontend confirm dialog states this before calling DELETE.
    """

    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='stock_categories')
    label = models.CharField(max_length=100)
    icon = models.CharField(max_length=50, help_text='A lucide-react icon component name (e.g. "Wheat").')
    sort_order = models.PositiveIntegerField(default=0)
    kind = models.CharField(
        max_length=16, choices=ItemCategory.choices, default=ItemCategory.CUSTOM,
        help_text='Discriminator for the four seeded defaults; user-added categories are CUSTOM.',
    )

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name_plural = 'stock categories'

    def __str__(self):
        return f'{self.farm_id} · {self.label}'


class FeedStage(models.TextChoices):
    STARTER = 'STARTER', 'Starter'
    GROWER = 'GROWER', 'Grower'
    FINISHER = 'FINISHER', 'Finisher'
    PULLET_STAGE = 'PULLET_STAGE', 'Pullet stage'
    LAYER_STAGE = 'LAYER_STAGE', 'Layer stage'
    NOT_APPLICABLE = 'NOT_APPLICABLE', 'Not applicable'


class Supplier(models.Model):
    """A supplier in the farm's directory (2026-08-28). New table, deliberately separate from
    the pre-existing free-text `PurchaseOrder.supplier` / `StockMovement.supplier` fields, which
    stay unchanged — a future task could migrate those to reference this row (see
    docs/deviations.md). `StockItem.supplier` points here for an item's default/primary supplier.
    """

    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='suppliers')
    name = models.CharField(max_length=255)
    contact = models.CharField(max_length=64, blank=True, help_text='Phone number.')
    email = models.EmailField(blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


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
    category = models.ForeignKey('stock.StockCategory', on_delete=models.CASCADE, related_name='items')
    name = models.CharField(max_length=255)
    unit = models.CharField(max_length=16)
    # Free-text-with-suggestions "type" of the article (2026-08-31). Stock items are
    # heterogeneous — feed and drugs, but also plain objects (a chair, a sponge…) — so the four
    # fixed categories aren't enough to say what a thing is. Purely a per-item label the user
    # picks from datalist presets or types themselves; it refines which ExpenseCategory an
    # auto-recorded stock purchase lands in (apps.stock.purchasing.record_manual_purchase_expense),
    # falling back to the category kind when blank/unrecognised.
    item_type = models.CharField(max_length=64, blank=True, default='')
    feed_stage = models.CharField(max_length=16, choices=FeedStage.choices, default=FeedStage.NOT_APPLICABLE)
    cold_chain_required = models.BooleanField(default=False)
    alert_threshold = models.FloatField(default=0)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    supplier = models.ForeignKey(
        Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name='items',
        help_text="Default/primary supplier for this item (2026-08-28). Free-text supplier fields "
                   "on PurchaseOrder/StockMovement are unaffected.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['category__sort_order', 'name']

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
    triggers a LOW_STOCK check for its item via the `on_stock_movement_saved` signal.

    `protocol_line` (2026-08-28) records which `ProtocolTemplate` row a consumption `OUT`
    originated from. It is set when a task occurrence is validated ("Marquer comme fait", 2026-
    08-31) for a row that has a linked resource + quantity, so a movement can be traced back to
    the task that caused it. (The 2026-08-28 automatic daily deduction that also set this field
    was removed 2026-08-31 — stock is now only ever deducted by an explicit user action.)
    `supplier` (free text) stays untouched by this."""

    item = models.ForeignKey(StockItem, on_delete=models.CASCADE, related_name='movements')
    batch = models.ForeignKey(PoultryBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_movements')
    protocol_line = models.ForeignKey(
        'protocols.ProtocolTemplate', on_delete=models.SET_NULL, null=True, blank=True, related_name='stock_movements',
    )
    movement_type = models.CharField(max_length=4, choices=MovementType.choices)
    quantity = models.FloatField()
    movement_date = models.DateField()
    supplier_batch_number = models.CharField(max_length=100, blank=True)
    supplier = models.CharField(max_length=255, blank=True)
    # Free-text note for a manual entry (2026-08-30) — e.g. why stock was added outside the
    # PurchaseOrder receiving flow ("don gouvernemental", "correction d'inventaire"). Blank for
    # PurchaseOrder-received and protocol-generated rows.
    note = models.CharField(max_length=255, blank=True)
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


class StockComposition(models.Model):
    """A "recipe" (2026-08-31): combine quantities of existing StockItems into one output
    product — e.g. 1000 kg maïs + 1000 kg macabo → "Provende maison". Defining it writes NO
    StockMovement; only *executing* it (apps.stock.compositions.execute_composition) moves
    stock — one OUT per ingredient + one IN for `output_item`, in a single transaction.

    `output_item` may be an existing item or one created inline from the same select-or-create
    combobox the ingredients use. All FKs are `CASCADE`: deleting a StockItem that is an
    ingredient or the output of a composition removes that composition too (a recipe referencing
    a deleted item is meaningless), consistent with how `StockCategory` delete already cascades
    to its items.
    """

    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='stock_compositions')
    name = models.CharField(max_length=255)
    output_item = models.ForeignKey(
        StockItem, on_delete=models.CASCADE, related_name='compositions_as_output',
    )
    # "Rendement de base" (2026-08-31) — how many `output_item` units one recipe batch yields
    # for the `ingredients` quantities as entered. When set (> 0), adding this output item's
    # stock anywhere else ("Ajouter Ici!" / the "Mettre à jour le stock" modal) with the
    # "décompter les ingrédients" option on auto-deducts each ingredient scaled to the amount
    # added — ingredient.quantity * added / base_output_quantity — as if the recipe had been
    # executed for that amount (apps.stock.compositions.auto_deduct_ingredients_for_output).
    # Nullable so recipes created before this field keep working (the option is then disabled).
    base_output_quantity = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.farm_id} · {self.name}'


class StockCompositionIngredient(models.Model):
    """One input line of a `StockComposition`. `quantity` is the *base/reference* amount for the
    recipe — the execute form pre-fills it but the user can adjust it per run."""

    composition = models.ForeignKey(
        StockComposition, on_delete=models.CASCADE, related_name='ingredients',
    )
    item = models.ForeignKey(
        StockItem, on_delete=models.CASCADE, related_name='composition_ingredients',
    )
    quantity = models.FloatField()

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.composition_id} · {self.item_id} · {self.quantity}'
