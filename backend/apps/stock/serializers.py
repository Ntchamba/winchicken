from rest_framework import serializers

from apps.stock.calculations import current_quantity
from apps.stock.models import (
    STOCK_CATEGORY_ICON_CHOICES, StockCategory, StockComposition, StockCompositionIngredient,
    StockItem, StockMovement, Supplier, Vaccination,
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
    `on_stock_movement_saved` signal.

    `total_price` (2026-08-31) is write-only: the "Prix total payé" for a manual IN. When set,
    `StockMovementListCreateView.perform_create` also creates a matching `Expense` in the same
    transaction (see `apps.stock.purchasing.record_manual_purchase_expense`) — that is what
    makes the purchase visible in Finance. Ignored for OUT."""

    total_price = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=0, required=False, allow_null=True, write_only=True,
        help_text='"Prix total payé" for a manual IN — creates a matching Expense.',
    )

    class Meta:
        model = StockMovement
        fields = [
            'id', 'item', 'batch', 'movement_type', 'quantity', 'movement_date',
            'supplier_batch_number', 'supplier', 'note', 'total_price',
        ]
        read_only_fields = ['id']
        extra_kwargs = {
            'batch': {'help_text': 'Batch this movement is attributed to, if any (e.g. feed consumption); optional.'},
            'note': {'required': False, 'help_text': 'Free-text note for a manual IN entry made outside the PurchaseOrder flow.'},
        }

    def create(self, validated_data):
        validated_data.pop('total_price', None)  # consumed by the view, not a model field
        return super().create(validated_data)


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


class StockCompositionIngredientSerializer(serializers.ModelSerializer):
    """One ingredient row — write: `item` (item_code) + `quantity`; read adds the item's name,
    unit and current on-hand quantity so the "Exécuter" form can pre-fill and warn."""

    item_name = serializers.CharField(source='item.name', read_only=True)
    unit = serializers.CharField(source='item.unit', read_only=True)
    current_quantity = serializers.SerializerMethodField()

    class Meta:
        model = StockCompositionIngredient
        fields = ['id', 'item', 'item_name', 'unit', 'quantity', 'current_quantity']
        read_only_fields = ['id']

    def get_current_quantity(self, ingredient) -> float:
        return current_quantity(ingredient.item)


class StockCompositionSerializer(serializers.ModelSerializer):
    """GET/POST payload for /api/farms/{farmId}/stock-compositions/ — a recipe. POST creates the
    composition + its `ingredients` in one transaction; NO StockMovement is written here
    (defining a recipe ≠ executing it). `output_item` / each ingredient `item` is an existing
    StockItem code — the frontend creates any not-yet-existing item inline first via
    POST /api/farms/{id}/stock-items/, then sends its code."""

    ingredients = StockCompositionIngredientSerializer(many=True)
    output_item_name = serializers.CharField(source='output_item.name', read_only=True)
    output_item_unit = serializers.CharField(source='output_item.unit', read_only=True)

    class Meta:
        model = StockComposition
        fields = ['id', 'name', 'output_item', 'output_item_name', 'output_item_unit', 'ingredients']
        read_only_fields = ['id']

    def validate(self, attrs):
        if not attrs.get('ingredients'):
            raise serializers.ValidationError({'ingredients': 'Au moins un ingrédient est requis.'})
        return attrs

    def create(self, validated_data):
        from django.db import transaction

        ingredients = validated_data.pop('ingredients')
        with transaction.atomic():
            composition = StockComposition.objects.create(**validated_data)
            StockCompositionIngredient.objects.bulk_create(
                StockCompositionIngredient(composition=composition, **ing) for ing in ingredients
            )
        return composition
