from django.conf import settings
from django.db import models

from apps.batches.models import PoultryBatch
from apps.houses.models import PoultryHouse
from apps.stock.models import StockItem


class EquipmentFault(models.Model):
    """A reported equipment breakdown for a house. `fault_code` is server-generated
    (`FAULT-{houseCode}-{seq}`, see apps.maintenance.serializers.EquipmentFaultSerializer.create).
    `status` is a free-text field (default "REPORTED") rather than a TextChoices enum — kept
    free-text rather than retrofitted into an enum for this task, to avoid a data migration for
    whatever values already exist in a live install; the "Cas signalés" resolve action
    (2026-08-26, docs/deviations.md Part 16, Part D) sets it to the literal string "RESOLVED"
    and stamps `repaired_date`, via the `POST /api/equipment-faults/{faultCode}/resolve/`
    endpoint this task added — the cahier des charges section 8 permission-matrix row "Valider
    une tâche de maintenance" (Technician / assigned Worker) finally has an endpoint behind it."""

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
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_faults',
        help_text='Who called the resolve action (2026-08-27, "Historique" tab, docs/deviations.md — '
                   'Feature 5) — set only by EquipmentFaultResolveView, never by the plain create/update path.',
    )

    class Meta:
        ordering = ['-reported_date']

    def __str__(self):
        return self.fault_code


class UnusualCase(models.Model):
    """Free-text report of an abnormal observation on a batch (disease symptoms, behavior,
    etc.), reported by either the responsible Farmer or a Worker. `case_code` is server-generated
    (`CASE-{batchCode}-{seq}`, see apps.maintenance.serializers.UnusualCaseSerializer.create).

    `resolved`/`resolved_at` (2026-08-26, docs/deviations.md Part 16, Part D) — this model had no
    resolution concept at all before this task (unlike `EquipmentFault`, which already had a
    free-text `status` field, just no endpoint to change it — see that model's docstring); added
    here as the plain boolean this task's own wording anticipated ("e.g. a status field update").
    """

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
    resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_cases',
        help_text='Who called the resolve action (2026-08-27, "Historique" tab, docs/deviations.md — '
                   'Feature 5) — set only by UnusualCaseResolveView, never by the plain create/update path.',
    )

    class Meta:
        ordering = ['-case_date']

    def __str__(self):
        return self.case_code
