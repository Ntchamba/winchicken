from rest_framework import serializers

from apps.protocols.models import CUSTOM_CATEGORY_ICON_CHOICES, ProtocolCategory, ProtocolTemplate, ProtocolTimeSlot


class ProtocolCategorySerializer(serializers.ModelSerializer):
    """GET/POST payload for /api/houses/{houseCode}/protocol-categories/ — one protocol tab
    (default or custom). `icon` is a lucide-react icon component name, validated against the
    curated picker allow-list on create, not free text."""

    class Meta:
        model = ProtocolCategory
        fields = ['id', 'label', 'icon', 'sort_order']
        read_only_fields = ['id', 'sort_order']
        extra_kwargs = {
            'label': {'help_text': 'Tab name shown to the user (e.g. "Biosécurité").'},
            'icon': {'help_text': 'lucide-react icon component name from the curated picker list.'},
        }

    def validate_icon(self, value):
        if value not in CUSTOM_CATEGORY_ICON_CHOICES:
            raise serializers.ValidationError("Cette icône n'est pas dans la liste proposée.")
        return value

    def validate_label(self, value):
        if not value.strip():
            raise serializers.ValidationError('Le nom de la catégorie est requis.')
        return value.strip()


class ProtocolTimeSlotSerializer(serializers.ModelSerializer):
    """One `ProtocolTimeSlot` — a "07h00-09h00"-style window, nested (read AND write) under
    `ProtocolTemplateSerializer.time_slots` (Bug 1 fix, 2026-08-27, docs/deviations.md). `id` is
    read-only/informational only: `HouseProtocolView.put`/`OnboardingView.post` always fully
    delete-and-recreate a house's protocol lines (and, transitively, their time slots — CASCADE),
    matching the existing full-replace convention for `ProtocolTemplate` itself; the frontend
    never sends an existing slot's id back to update it in place."""

    class Meta:
        model = ProtocolTimeSlot
        fields = ['id', 'start_time', 'end_time']
        read_only_fields = ['id']

    def validate(self, attrs):
        if attrs['end_time'] <= attrs['start_time']:
            raise serializers.ValidationError("L'heure de fin doit être après l'heure de début.")
        return attrs


class ProtocolTemplateSerializer(serializers.ModelSerializer):
    """One protocol line, used by /api/houses/{houseCode}/protocol/. `category` is the
    ProtocolCategory's id (FK) — not a fixed enum value anymore. `to_value`/`to_unit` may be
    omitted when `until_end` is true. `time_slots` (2026-08-27) is optional and, per line, either
    empty (a day-range task with no specific time) or one-or-more `ProtocolTimeSlot` windows —
    see that model's docstring."""

    time_slots = ProtocolTimeSlotSerializer(many=True, required=False)

    class Meta:
        model = ProtocolTemplate
        fields = [
            'id', 'category', 'from_value', 'from_unit', 'to_value', 'to_unit', 'until_end',
            'what', 'details', 'time_slots', 'stock_item', 'quantity_per_day',
        ]
        read_only_fields = ['id']
        extra_kwargs = {
            'from_value': {'help_text': 'Start of the range, in from_unit (e.g. day 1).'},
            'to_value': {'help_text': 'End of the range, in to_unit; ignored/omit if until_end is true.'},
            'until_end': {'help_text': 'If true, the line applies from from_value until the end of the growth cycle.'},
            'what': {'help_text': 'Short label for the action (e.g. "Starter feed", "Newcastle disease").'},
            'details': {'help_text': 'Free-text detail (dosage, composition, notes).'},
            'stock_item': {
                'required': False, 'allow_null': True,
                'help_text': 'Optional StockItem this row consumes daily (with quantity_per_day).',
            },
            'quantity_per_day': {
                'required': False, 'allow_null': True,
                'help_text': 'Units/day of stock_item this row consumes (e.g. 40 kg/day of starter feed).',
            },
        }
