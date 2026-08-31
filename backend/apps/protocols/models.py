from django.conf import settings
from django.db import models

from apps.houses.models import PoultryHouse

# The 5 default categories seeded for every new PoultryHouse (apps.houses.signals) — structural
# UI scaffolding (empty of protocol lines), not example farm content, so seeding them
# automatically doesn't violate the no-default-data rule. `icon` values are lucide-react icon
# component names, resolved on the frontend via a lookup map — never rendered as raw text.
DEFAULT_PROTOCOL_CATEGORIES = [
    {'label': 'Alimentation', 'icon': 'Soup'},
    {'label': 'Température', 'icon': 'Thermometer'},
    {'label': 'Santé et soins', 'icon': 'Stethoscope'},
    {'label': 'Vaccination', 'icon': 'Syringe'},
    {'label': 'Nettoyage', 'icon': 'SprayCan'},
]

# Curated icon picker for custom categories (implementation-detail spec addendum, 2026-08-25)
# — kept in sync by hand with frontend/src/components/HouseProtocolForm.jsx's ICON_OPTIONS.
# The 5 default categories' own icons (above) are always valid too, even though a user can't
# pick them again for a *new* category through this list (nothing stops them from choosing the
# same icon as a default for a custom category — only the icon *name* is validated, not
# uniqueness).
CUSTOM_CATEGORY_ICON_CHOICES = [
    'Soup', 'Thermometer', 'Stethoscope', 'Syringe', 'SprayCan',
    'ShieldCheck', 'Droplets', 'Wind', 'Egg', 'Bug', 'ClipboardList', 'Package',
]


class ProtocolCategory(models.Model):
    """A protocol tab for one house — the 5 defaults (Alimentation/Température/Santé et
    soins/Vaccination/Nettoyage) plus any custom categories a user adds via
    POST /api/houses/{houseCode}/protocol-categories/. Replaces the fixed 5-value
    `ProtocolCategory` TextChoices enum this model used to be (implementation-detail spec
    update, 2026-08-25) — `ProtocolTemplate.category` is now a FK to this table instead of a
    hardcoded string, so a house can have more than the 5 defaults.

    Deleting a category cascades to delete its ProtocolTemplate rows (`ProtocolTemplate.category`
    is `on_delete=CASCADE`) — enforced at the DB level, not just a confirm dialog on the frontend.
    """

    house = models.ForeignKey(PoultryHouse, on_delete=models.CASCADE, related_name='protocol_categories')
    label = models.CharField(max_length=100)
    icon = models.CharField(max_length=50, help_text='A lucide-react icon component name (e.g. "Soup").')
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'id']
        verbose_name_plural = 'protocol categories'

    def __str__(self):
        return f'{self.house_id} · {self.label}'


class ProtocolUnit(models.TextChoices):
    DAY = 'DAY', 'Day'
    WEEK = 'WEEK', 'Week'
    MONTH = 'MONTH', 'Month'


class ProtocolTemplate(models.Model):
    """Reusable protocol line for a house (e.g. "Starter feed, day 1 to 15"), applied to every
    batch started there. Not present in `farm_management_schema_en.puml` at all before this
    change — the puml predates this app; the cahier des charges section 10 table does list it
    under `protocols`. `farm_management_schema_en.puml` now documents `ProtocolCategory` too.

    A house is considered "configured" for onboarding purposes once it has at least one
    ProtocolTemplate line (see `apps.core.services.is_farm_configured` — the schema has no
    boolean "active" flag on this model to check instead).

    `to_value`/`to_unit` are ignored when `until_end` is True (the line runs to the end of the
    cycle instead of a fixed bound) — enforced by the frontend form, not a DB constraint.

    `assigned_to` (2026-08-26, docs/deviations.md Part 15) is the task-assignment target for
    this line's occurrences in "tâches à effectuer maintenant" (`apps.houses.views.
    HouseTasksNowView` reuses this line's own row as the one persisted "task" identity, matching
    how it's already keyed by `line.id` there). Purely additive — `null` still shows normally
    for anyone with house access, only Admin/Farm Manager/Farmer (`CanEditHouseProtocol`) can
    set it. Known limitation, accepted rather than engineered around: `HouseProtocolView.put`
    does a full delete-and-recreate of a house's `ProtocolTemplate` rows on every protocol save
    (see that view), so any assignment is cleared the next time the protocol is edited at all,
    not just the assigned line — the same full-replace semantics the rows themselves already
    have, not a new fragility this field introduces.
    """

    house = models.ForeignKey(PoultryHouse, on_delete=models.CASCADE, related_name='protocol_lines')
    category = models.ForeignKey(ProtocolCategory, on_delete=models.CASCADE, related_name='protocol_lines')
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_protocol_tasks',
    )
    from_value = models.PositiveIntegerField()
    from_unit = models.CharField(max_length=8, choices=ProtocolUnit.choices, default=ProtocolUnit.DAY)
    to_value = models.PositiveIntegerField(null=True, blank=True)
    to_unit = models.CharField(max_length=8, choices=ProtocolUnit.choices, default=ProtocolUnit.DAY)
    until_end = models.BooleanField(default=False)
    what = models.CharField(max_length=255)
    details = models.CharField(max_length=500, blank=True)
    # Optional stock consumption: a row can declare "doing this task consumes `stock_item`".
    # `quantity_per_day` is the amount consumed per validated occurrence — despite the legacy
    # name it is NOT time-based: as of 2026-08-31 stock is deducted only when the occurrence is
    # marked done ("Marquer comme fait" → apps.stock.services_consumption), never because a day
    # passed. `dose_per_bird` (× batch.current_count) is the per-bird alternative. At most one
    # is set (ProtocolTemplateSerializer.validate); both null for non-consumption rows. Also
    # feeds the config-time insufficient-stock warning (apps.stock.calculations.coverage_for).
    # (The 2026-08-28 automatic daily Celery deduction was removed 2026-08-31.)
    stock_item = models.ForeignKey(
        'stock.StockItem', on_delete=models.SET_NULL, null=True, blank=True, related_name='protocol_lines',
    )
    quantity_per_day = models.FloatField(null=True, blank=True)
    dose_per_bird = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['category__sort_order', 'from_value']

    def __str__(self):
        return f'{self.house_id} · {self.category_id} · {self.what}'


class ProtocolTimeSlot(models.Model):
    """A time window a `ProtocolTemplate` line recurs at on each of its due days (e.g. feeding
    07h00-09h00 and 18h00-20h00) — added 2026-08-27 for `apps.alerts.templates.
    build_task_reminders`, which generates one correctly-timed personal reminder per slot
    (keyed off `start_time` — see that module) instead of one reminder with no time or an
    ambiguous combined one; a line with no rows here is a day-range task with no specific time
    (renders "...aujourd'hui" instead).

    `end_time` (2026-08-27 bugfix, docs/deviations.md — "Bug 1") was added once the "Modifier"
    UI for these was actually built: the frontend shows each slot as a removable "07h00–09h00"
    chip and needs both ends of the window to render/validate it, even though the SMS reminder
    template still only ever reads `start_time` (unchanged, per that task's own "don't touch
    SMS/notification logic" rule).

    Editable via the shared `HouseProtocolForm` component (onboarding step 1 and the "Modifier"
    edit modal/page) — see `apps.protocols.serializers.ProtocolTimeSlotSerializer` and
    `apps.houses.views.protocol.HouseProtocolView`/`apps.protocols.views.OnboardingView` for how
    they're written.
    """

    protocol_line = models.ForeignKey(ProtocolTemplate, on_delete=models.CASCADE, related_name='time_slots')
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ['start_time']

    def __str__(self):
        return f'{self.protocol_line_id} · {self.start_time}-{self.end_time}'
