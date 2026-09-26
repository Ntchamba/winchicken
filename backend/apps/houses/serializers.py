from rest_framework import serializers

from apps.core.codes import create_with_code, next_sequential_code
from apps.houses.models import PoultryHouse


def generate_house_code(farm_id):
    """Builds the next `H-{farmId}-{seq}` code for a farm — one past the highest in use, never a
    row count (a count reissues a live code after any deletion; see apps.core.codes)."""
    return next_sequential_code(PoultryHouse, 'house_code', f'H-{farm_id}-')


class PoultryHouseSerializer(serializers.ModelSerializer):
    """GET/POST/PATCH payload for /api/houses/ and /api/houses/{houseCode}/.
    `house_code` is always server-generated on create — never accepted from the client."""

    class Meta:
        model = PoultryHouse
        fields = ['house_code', 'name', 'size_m2', 'max_capacity', 'last_disinfection_date', 'created_at']
        read_only_fields = ['house_code', 'created_at']
        extra_kwargs = {
            'size_m2': {'help_text': 'Floor area in square meters; optional.'},
            'max_capacity': {'help_text': 'Maximum number of birds this house can hold.'},
            'last_disinfection_date': {'help_text': 'Date of the last sanitary-void disinfection, if any.'},
        }

    def validate_name(self, value):
        # Two houses with the same name was always a mistake, never a layout: a first-time user
        # who stepped back to "1. Bâtiments" to fix something and pressed "Suivant" again got a
        # second "Bâtiment 1" with a second batch, silently (campaign 9, finding B17).
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Le nom du bâtiment est requis.")
        request = self.context.get('request')
        farm = getattr(getattr(request, 'user', None), 'farm', None)
        if farm is not None:
            clash = PoultryHouse.objects.filter(farm=farm, name__iexact=value)
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError(f"Un bâtiment s'appelle déjà « {value} ».")
        return value

    def create(self, validated_data):
        farm = self.context['request'].user.farm
        validated_data['farm'] = farm

        def create():
            validated_data['house_code'] = generate_house_code(farm.id)
            return super(PoultryHouseSerializer, self).create(validated_data)
        return create_with_code(create)
