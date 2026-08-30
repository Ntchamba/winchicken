from rest_framework import serializers

from apps.stock.calculations import current_quantity
from apps.stock.models import (
    STOCK_CATEGORY_ICON_CHOICES, StockCategory, StockItem, StockMovement, Supplier, Vaccination,
)


class StockCategorySerializer(serializers.ModelSerializer):
    """GET/POST payload for /api/farms/{farmId}/stock-categories/ — one stock parameter tab
    (default or custom). `icon` is a lucide-react icon component name, validated against the
    curated picker allow-list on create. `kind` is read-only: it is `CUSTOM` for anything a
    user adds; only the four per-farm seeded rows carry FEED/VETERINARY/EQUIPMENT/BEDDING."""

    class Meta:
        model = StockCategory
        fields = ['id', 'label', 'icon', 'sort_order', 'kind']
        read_only_fields = ['id', 'sort_order', 'kind']

    def validate_icon(self, value):
        if value not in STOCK_CATEGORY_ICON_CHOICES:
            raise serializers.ValidationError("Cette icône n'est pas dans la liste proposée.")
        return value

    def validate_label(self, value):
        if not value.strip():
            raise serializers.ValidationError('Le nom de la catégorie est requis.')
        return value.strip()


class SupplierSerializer(serializers.ModelSerializer):
    """GET/POST/PUT payload for /api/farms/{farmId}/suppliers/ and /api/suppliers/{id}/.
    `item_names` is derived read-only — the StockItem rows whose default supplier is this row."""

    item_names = serializers.SerializerMethodField()

    class Meta:
        model = Supplier
        fields = ['id', 'name', 'contact', 'email', 'item_names']
        read_only_fields = ['id', 'item_names']

    def get_item_names(self, supplier) -> list:
        return [item.name for item in supplier.items.all()]

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError('Le nom du fournisseur est requis.')
        return value.strip()


class StockItemSerializer(serializers.ModelSerializer):
    """One warehouse item definition, used both by /api/farms/{farmId}/stock-items/ (bulk
    onboarding/replace) and embedded in the "items" list of that payload."""

    current_quantity = serializers.SerializerMethodField(
        help_text='Computed on the fly by apps.stock.calculations.current_quantity — never stored.'
    )
    category_label = serializers.CharField(source='category.label', read_only=True)
    category_kind = serializers.CharField(source='category.kind', read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True, default=None)

    class Meta:
        model = StockItem
        fields = [
            'item_code', 'category', 'category_label', 'category_kind', 'name', 'unit',
            'feed_stage', 'cold_chain_required', 'alert_threshold', 'unit_price',
            'current_quantity', 'supplier', 'supplier_name',
        ]
        read_only_fields = ['item_code']
        extra_kwargs = {
            'alert_threshold': {'help_text': 'LOW_STOCK alert fires when current_quantity drops below this value.'},
            'supplier': {'required': False, 'allow_null': True},
        }

    def get_current_quantity(self, item) -> float:
        return current_quantity(item)


_KIND_PREFIX = {'FEED': 'FEE', 'VETERINARY': 'VET', 'EQUIPMENT': 'EQU', 'BEDDING': 'BED', 'CUSTOM': 'CUS'}


def generate_item_code(farm_id, category):
    """Builds the next `{PREFIX}-{farmId}-{seq}` code, scoped per farm and per category
    (e.g. `FEE-1-001`) — counts existing rows for that farm+category rather than a persisted
    counter. `category` is a `StockCategory` instance; the 3-letter prefix comes from its
    `kind` (`CUS` for user-added categories)."""
    count = StockItem.objects.filter(farm_id=farm_id, category=category).count() + 1
    prefix = _KIND_PREFIX.get(category.kind, 'CUS')
    return f'{prefix}-{farm_id}-{count:03d}'


class StockMovementSerializer(serializers.ModelSerializer):
    """GET/POST payload for /api/stock-movements/ — one IN (restocking) or OUT (consumption) row.
    Saving one triggers `apps.alerts.services.check_low_stock` for `item` via the
    `on_stock_movement_saved` signal."""

    class Meta:
        model = StockMovement
        fields = [
            'id', 'item', 'batch', 'movement_type', 'quantity', 'movement_date',
            'supplier_batch_number', 'supplier', 'note',
        ]
        read_only_fields = ['id']
        extra_kwargs = {
            'batch': {'help_text': 'Batch this movement is attributed to, if any (e.g. feed consumption); optional.'},
            'note': {'required': False, 'help_text': 'Free-text note for a manual IN entry made outside the PurchaseOrder flow.'},
        }


class VaccinationSerializer(serializers.ModelSerializer):
    """GET/POST payload for /api/vaccinations/. `doses_used` must be greater than or equal to
    the batch's current bird count (see `validate` below) — reflects the schema rule that a
    vaccine vial, once reconstituted, is used for the whole flock rather than partially."""

    class Meta:
        model = Vaccination
        fields = [
            'id', 'batch', 'item', 'scheduled_date', 'administered_date',
            'reconstitution_time', 'doses_used', 'status',
        ]
        read_only_fields = ['id']
        extra_kwargs = {
            'reconstitution_time': {'help_text': 'When the vaccine vial was reconstituted; strict expiry is reconstitution_time + 2h (enforced by convention, not a DB constraint).'},
        }

    def validate(self, attrs):
        batch = attrs.get('batch') or getattr(self.instance, 'batch', None)
        doses_used = attrs.get('doses_used')
        if batch and doses_used is not None and doses_used < batch.current_count:
            raise serializers.ValidationError(
                {'doses_used': "Le nombre de doses utilisées doit être supérieur ou égal à l'effectif actuel de la bande."}
            )
        return attrs
