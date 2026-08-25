from rest_framework import serializers

from apps.maintenance.models import EquipmentFault, UnusualCase


class EquipmentFaultSerializer(serializers.ModelSerializer):
    """GET/POST payload for /api/equipment-faults/. `fault_code` and `reported_date` are always
    server-generated; there is no update endpoint to move `status` past its default "REPORTED"
    (see EquipmentFault model docstring)."""

    class Meta:
        model = EquipmentFault
        fields = ['fault_code', 'technician', 'house', 'item', 'fault_description', 'reported_date', 'repaired_date', 'status']
        read_only_fields = ['fault_code', 'reported_date']
        extra_kwargs = {
            'item': {'help_text': 'StockItem (category EQUIPMENT) concerned by the fault, if applicable.'},
        }

    def create(self, validated_data):
        count = EquipmentFault.objects.filter(house=validated_data['house']).count() + 1
        validated_data['fault_code'] = f"FAULT-{validated_data['house'].house_code}-{count:03d}"
        return super().create(validated_data)


class UnusualCaseSerializer(serializers.ModelSerializer):
    """GET/POST payload for /api/unusual-cases/. `case_code` and `case_date` are always
    server-generated."""

    class Meta:
        model = UnusualCase
        fields = ['case_code', 'batch', 'farmer', 'worker', 'case_description', 'case_date']
        read_only_fields = ['case_code', 'case_date']

    def create(self, validated_data):
        count = UnusualCase.objects.filter(batch=validated_data['batch']).count() + 1
        validated_data['case_code'] = f"CASE-{validated_data['batch'].batch_code}-{count:03d}"
        return super().create(validated_data)
