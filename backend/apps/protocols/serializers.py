from rest_framework import serializers

from apps.protocols.models import CUSTOM_CATEGORY_ICON_CHOICES, ProtocolCategory, ProtocolTemplate


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


class ProtocolTemplateSerializer(serializers.ModelSerializer):
    """One protocol line, used by /api/houses/{houseCode}/protocol/. `category` is the
    ProtocolCategory's id (FK) — not a fixed enum value anymore. `to_value`/`to_unit` may be
    omitted when `until_end` is true."""

    class Meta:
        model = ProtocolTemplate
        fields = ['id', 'category', 'from_value', 'from_unit', 'to_value', 'to_unit', 'until_end', 'what', 'details']
        read_only_fields = ['id']
        extra_kwargs = {
            'from_value': {'help_text': 'Start of the range, in from_unit (e.g. day 1).'},
            'to_value': {'help_text': 'End of the range, in to_unit; ignored/omit if until_end is true.'},
            'until_end': {'help_text': 'If true, the line applies from from_value until the end of the growth cycle.'},
            'what': {'help_text': 'Short label for the action (e.g. "Starter feed", "Newcastle disease").'},
            'details': {'help_text': 'Free-text detail (dosage, composition, notes).'},
        }
