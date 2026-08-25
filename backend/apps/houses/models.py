from django.db import models

from apps.core.models import Farm


class PoultryHouse(models.Model):
    """A physical building on the farm; hosts one ProtocolTemplate (feeding/health/etc. schedule)
    and, over time, a sequence of PoultryBatch rows — but only one ACTIVE batch at a time
    (enforced at apps.batches.models.PoultryBatch level, sanitary-void principle).

    `house_code` is server-generated (`H-{farmId}-{seq}`, see
    apps.houses.serializers.generate_house_code) — no form collects it manually.
    """

    house_code = models.CharField(max_length=32, primary_key=True)
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='houses')
    name = models.CharField(max_length=255)
    size_m2 = models.PositiveIntegerField(null=True, blank=True)
    max_capacity = models.PositiveIntegerField()
    last_disinfection_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return self.name
