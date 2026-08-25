from rest_framework import serializers

from apps.stock.calculations import current_quantity
from apps.stock.models import StockItem, StockMovement, Vaccination


class StockItemSerializer(serializers.ModelSerializer):
    """One warehouse item definition, used both by /api/farms/{farmId}/stock-items/ (bulk
    onboarding/replace) and embedded in the "items" list of that payload."""

    current_quantity = serializers.SerializerMethodField(
        help_text='Computed on the fly by apps.stock.calculations.current_quantity — never stored.'
    )

    class Meta:
        model = StockItem
        fields = [
            'item_code', 'category', 'name', 'unit', 'feed_stage', 'cold_chain_required',
            'alert_threshold', 'unit_price', 'current_quantity',
        ]
        read_only_fields = ['item_code']
        extra_kwargs = {
            'alert_threshold': {'help_text': 'LOW_STOCK alert fires when current_quantity drops below this value.'},
        }

    def get_current_quantity(self, item) -> float:
        return current_quantity(item)


def generate_item_code(farm_id, category):
    """Builds the next `{CAT3}-{farmId}-{seq}` code, scoped per farm and per category
    (e.g. `FEE-1-001`) — counts existing rows for that farm+category rather than a persisted counter."""
    count = StockItem.objects.filter(farm_id=farm_id, category=category).count() + 1
    return f'{category[:3]}-{farm_id}-{count:03d}'


class StockMovementSerializer(serializers.ModelSerializer):
    """GET/POST payload for /api/stock-movements/ — one IN (restocking) or OUT (consumption) row.
    Saving one triggers `apps.alerts.services.check_low_stock` for `item` via the
    `on_stock_movement_saved` signal."""

    class Meta:
        model = StockMovement
        fields = [
            'id', 'item', 'batch', 'movement_type', 'quantity', 'movement_date',
            'supplier_batch_number', 'supplier',
        ]
        read_only_fields = ['id']
        extra_kwargs = {
            'batch': {'help_text': 'Batch this movement is attributed to, if any (e.g. feed consumption); optional.'},
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
