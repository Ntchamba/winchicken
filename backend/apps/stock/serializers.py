from rest_framework import serializers

from apps.core.fields import FiniteFloatField
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
            'item_code', 'category', 'category_label', 'category_kind', 'name', 'unit', 'item_type',
            'feed_stage', 'cold_chain_required', 'alert_threshold', 'unit_price',
            'current_quantity', 'supplier', 'supplier_name',
        ]
        read_only_fields = ['item_code']
        # min_value 0 on both: the stock form's PUT and the Excel import (which reuses this
        # serializer) stored a -50 threshold and a -100 FCFA unit price (campaign 9, finding B9) —
        # a negative price turns every purchase-order and valuation figure built on it negative.
        extra_kwargs = {
            'alert_threshold': {
                'min_value': 0,
                'help_text': 'An article is low (badge, overview, LOW_STOCK alert) when current_quantity is at or under this value.',
            },
            'unit_price': {'min_value': 0},
            'supplier': {'required': False, 'allow_null': True},
        }

    def get_current_quantity(self, item) -> float:
        return current_quantity(item)


_KIND_PREFIX = {'FEED': 'FEE', 'VETERINARY': 'VET', 'EQUIPMENT': 'EQU', 'BEDDING': 'BED', 'CUSTOM': 'CUS'}


def generate_item_code(farm_id, category):
    """Builds the next `{PREFIX}-{farmId}-{seq}` code (e.g. `FEE-1-001`) — one past the highest
    in use under that prefix. `category` is a `StockCategory` instance; the 3-letter prefix comes
    from its `kind` (`CUS` for user-added categories). It used to count the *category's* rows,
    which collided both after a deletion and between two custom categories sharing `CUS`
    (see apps.core.codes)."""
    from apps.core.codes import next_sequential_code
    prefix = _KIND_PREFIX.get(category.kind, 'CUS')
    return next_sequential_code(StockItem, 'item_code', f'{prefix}-{farm_id}-')


def next_free_item_code(farm_id, category, taken):
    """Like `generate_item_code` but skips any code already in `taken`. Needed by the
    /stock-items/ PUT: `generate_item_code` derives the sequence number from a row *count*, so
    it cannot see a code that is about to be taken by another row in the same request, and a
    new article would be handed a code that collides with a kept one (the actual cause of the
    500 on "add an article"). `taken` therefore carries both the codes already in the database
    and every code this request keeps."""
    prefix = _KIND_PREFIX.get(category.kind, 'CUS')
    seq = 1
    while True:
        code = f'{prefix}-{farm_id}-{seq:03d}'
        if code not in taken:
            return code
        seq += 1


class StockItemRowSerializer(StockItemSerializer):
    """One row of the stock parameters PUT, validated for its own values only — category and
    supplier are resolved (and farm-checked) by the view, `item_code` matches the row. Same
    field rules as `StockItemSerializer` (which the Excel import uses), except that `unit` may be
    left blank here, as the form always could."""

    class Meta(StockItemSerializer.Meta):
        fields = ['name', 'unit', 'item_type', 'feed_stage', 'cold_chain_required', 'alert_threshold', 'unit_price']
        extra_kwargs = {
            **StockItemSerializer.Meta.extra_kwargs,
            'unit': {'required': False, 'allow_blank': True},
        }


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
    production_quantity = FiniteFloatField(
        min_value=0, required=False, allow_null=True, write_only=True,
        help_text='When this IN adds a composition\'s output item and the "décompter les '
                  'ingrédients" option is on: the output amount to treat as produced, so the '
                  'recipe ingredients are deducted scaled to it (apps.stock.compositions).',
    )

    class Meta:
        model = StockMovement
        fields = [
            'id', 'item', 'batch', 'movement_type', 'quantity', 'movement_date',
            'supplier_batch_number', 'supplier', 'note', 'total_price', 'production_quantity',
        ]
        read_only_fields = ['id']
        extra_kwargs = {
            'batch': {'help_text': 'Batch this movement is attributed to, if any (e.g. feed consumption); optional.'},
            'note': {'required': False, 'help_text': 'Free-text note for a manual IN entry made outside the PurchaseOrder flow.'},
        }

    # A manual movement had no bounds at all: an IN of -5 (a hidden OUT that bypassed every
    # shortfall warning) and a movement dated 2200 were both stored (campaign 9, finding B6).
    # The date rule is the one sales and expenses already use.
    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("La quantité doit être supérieure à 0.")
        return value

    def validate_movement_date(self, value):
        from apps.finance.serializers import _not_in_the_future
        return _not_in_the_future(value, "La date du mouvement ne peut pas être dans le futur.")

    def create(self, validated_data):
        validated_data.pop('total_price', None)         # consumed by the view, not model fields
        validated_data.pop('production_quantity', None)
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
        fields = [
            'id', 'name', 'output_item', 'output_item_name', 'output_item_unit',
            'base_output_quantity', 'ingredients',
        ]
        read_only_fields = ['id']
        extra_kwargs = {'base_output_quantity': {'required': False, 'allow_null': True}}

    def validate_base_output_quantity(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError('Le rendement de base doit être positif.')
        return value

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
