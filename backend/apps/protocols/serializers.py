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
    `ProtocolTemplateSerializer.time_slots` (Bug 1 fix, 2026-08-27, docs/deviations.md).

    `id` stays read-only and the frontend still never sends one back: since FIX 3.5
    `HouseProtocolView.put` matches a slot on `(start_time, end_time)`, which is what a slot
    actually *is*. That matters because `TaskCompletion.time_slot` is CASCADE — replacing a
    line's slots on every save would destroy the completions keyed on them even when the line
    itself survived. Editing a window's times is still a delete + create, and takes that
    window's completions with it, which is correct: it is a different occurrence."""

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
    # Writable so `HouseProtocolView.put` can match a submitted line back to the row it edits.
    # It is the only natural key a protocol line has — every other field is user-editable, so
    # matching on `what` or the day range would read a renamed line as "delete + create" and
    # take its completion history with it. Omit it and the line is created; a line the client
    # omits entirely is the one that gets deleted (FIX 3.5, bug A).
    id = serializers.IntegerField(required=False)

    class Meta:
        model = ProtocolTemplate
        fields = [
            'id', 'category', 'from_value', 'from_unit', 'to_value', 'to_unit', 'until_end',
            'what', 'details', 'time_slots', 'stock_item', 'quantity_per_day', 'dose_per_bird',
        ]
        extra_kwargs = {
            'from_value': {'help_text': 'Start of the range, in from_unit (e.g. day 1).'},
            'to_value': {'help_text': 'End of the range, in to_unit; ignored/omit if until_end is true.'},
            'until_end': {'help_text': 'If true, the line applies from from_value until the end of the growth cycle.'},
            'what': {'help_text': 'Short label for the action (e.g. "Starter feed", "Newcastle disease").'},
            'details': {'help_text': 'Free-text detail (dosage, composition, notes).'},
            'stock_item': {
                'required': False, 'allow_null': True,
                'help_text': 'Optional StockItem this row consumes daily (with quantity_per_day OR dose_per_bird).',
            },
            'quantity_per_day': {
                'required': False, 'allow_null': True,
                'help_text': 'Dosage mode "Quantité fixe / jour": a fixed amount/day of stock_item '
                             '(e.g. 40 kg/day of starter feed). Mutually exclusive with dose_per_bird.',
            },
            'dose_per_bird': {
                'required': False, 'allow_null': True,
                'help_text': 'Dosage mode "Dose par bande": amount per live bird; the daily movement is '
                             'dose_per_bird * batch.current_count. Mutually exclusive with quantity_per_day.',
            },
        }

    def validate(self, attrs):
        # Merge over the instance so a partial update can't slip past the mutual-exclusion check.
        quantity_per_day = attrs.get('quantity_per_day', getattr(self.instance, 'quantity_per_day', None))
        dose_per_bird = attrs.get('dose_per_bird', getattr(self.instance, 'dose_per_bird', None))
        stock_item = attrs.get('stock_item', getattr(self.instance, 'stock_item', None))

        if quantity_per_day is not None and dose_per_bird is not None:
            raise serializers.ValidationError(
                "Choisissez un seul mode de dosage : « Quantité fixe / jour » ou « Dose par bande », pas les deux."
            )
        if (quantity_per_day is not None or dose_per_bird is not None) and stock_item is None:
            raise serializers.ValidationError(
                "Renseignez l'article de stock consommé avant d'indiquer une quantité ou une dose."
            )
        return attrs
