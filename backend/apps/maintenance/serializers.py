from rest_framework import serializers

from apps.maintenance.models import EquipmentFault, UnusualCase


class EquipmentFaultSerializer(serializers.ModelSerializer):
    """GET/POST payload for /api/equipment-faults/. `fault_code` and `reported_date` are always
    server-generated. `houseName`/`technicianName` (2026-08-26, "Cas signalés" — docs/
    deviations.md Part 16) are read-only display conveniences for the incident card, so the
    frontend doesn't need a second round-trip to resolve `house`/`technician` ids to names."""

    houseName = serializers.CharField(source='house.name', read_only=True)
    technicianName = serializers.CharField(source='technician.name', read_only=True, default=None)
    resolvedByName = serializers.CharField(source='resolved_by.name', read_only=True, default=None)

    class Meta:
        model = EquipmentFault
        fields = [
            'fault_code', 'technician', 'technicianName', 'house', 'houseName', 'item',
            'fault_description', 'reported_date', 'repaired_date', 'status', 'resolved_by', 'resolvedByName',
        ]
        read_only_fields = ['fault_code', 'reported_date', 'resolved_by']
        extra_kwargs = {
            'item': {'help_text': 'StockItem (category EQUIPMENT) concerned by the fault, if applicable.'},
        }

    def create(self, validated_data):
        count = EquipmentFault.objects.filter(house=validated_data['house']).count() + 1
        validated_data['fault_code'] = f"FAULT-{validated_data['house'].house_code}-{count:03d}"
        return super().create(validated_data)


class UnusualCaseSerializer(serializers.ModelSerializer):
    """GET/POST payload for /api/unusual-cases/. `case_code` and `case_date` are always
    server-generated. `houseCode`/`houseName`/`batchName`/`reporterName` (2026-08-26, "Cas
    signalés") are read-only display conveniences, same reasoning as `EquipmentFaultSerializer`
    above. `reporterName` reads whichever of `farmer`/`worker` is actually set — exactly one of
    the two ever is, per how this model's own two FKs are used."""

    houseCode = serializers.CharField(source='batch.house_id', read_only=True)
    houseName = serializers.CharField(source='batch.house.name', read_only=True)
    batchName = serializers.CharField(source='batch.name', read_only=True)
    reporterName = serializers.SerializerMethodField()
    resolvedByName = serializers.CharField(source='resolved_by.name', read_only=True, default=None)

    class Meta:
        model = UnusualCase
        fields = [
            'case_code', 'batch', 'houseCode', 'houseName', 'batchName', 'farmer', 'worker',
            'reporterName', 'case_description', 'case_date', 'resolved', 'resolved_at',
            'resolved_by', 'resolvedByName',
        ]
        read_only_fields = ['case_code', 'case_date', 'resolved', 'resolved_at', 'resolved_by']

    def get_reporterName(self, obj) -> str:
        reporter = obj.farmer or obj.worker
        return reporter.name if reporter else None

    def create(self, validated_data):
        count = UnusualCase.objects.filter(batch=validated_data['batch']).count() + 1
        validated_data['case_code'] = f"CASE-{validated_data['batch'].batch_code}-{count:03d}"
        return super().create(validated_data)
