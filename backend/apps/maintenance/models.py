from django.conf import settings
from django.db import models

from apps.batches.models import PoultryBatch
from apps.houses.models import PoultryHouse
from apps.stock.models import StockItem


class EquipmentFault(models.Model):
    """A reported equipment breakdown for a house. `fault_code` is server-generated
    (`FAULT-{houseCode}-{seq}`, see apps.maintenance.serializers.EquipmentFaultSerializer.create).
    `status` is a free-text field (default "REPORTED") rather than a TextChoices enum — there is
    no dedicated "validate a maintenance task" endpoint in this app despite the cahier des
    charges section 8 permission-matrix row "Valider une tâche de maintenance" (Technician /
    assigned Worker); status transitions happen via a plain PATCH on this model's fields if
    exposed, but no such PATCH endpoint currently exists (see docs/deviations.md)."""

    fault_code = models.CharField(max_length=32, primary_key=True)
    technician = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='handled_faults'
    )
    house = models.ForeignKey(PoultryHouse, on_delete=models.CASCADE, related_name='equipment_faults')
    item = models.ForeignKey(StockItem, on_delete=models.SET_NULL, null=True, blank=True, related_name='equipment_faults')
    fault_description = models.CharField(max_length=1000)
    reported_date = models.DateField(auto_now_add=True)
    repaired_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=32, default='REPORTED')

    class Meta:
        ordering = ['-reported_date']

    def __str__(self):
        return self.fault_code


class UnusualCase(models.Model):
    """Free-text report of an abnormal observation on a batch (disease symptoms, behavior,
    etc.), reported by either the responsible Farmer or a Worker. `case_code` is server-generated
    (`CASE-{batchCode}-{seq}`, see apps.maintenance.serializers.UnusualCaseSerializer.create)."""

    case_code = models.CharField(max_length=32, primary_key=True)
    batch = models.ForeignKey(PoultryBatch, on_delete=models.CASCADE, related_name='unusual_cases')
    farmer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reported_cases_as_farmer'
    )
    worker = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reported_cases_as_worker'
    )
    case_description = models.CharField(max_length=1000)
    case_date = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ['-case_date']

    def __str__(self):
        return self.case_code
