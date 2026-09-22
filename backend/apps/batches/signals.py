from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.batches.models import PoultryBatch


@receiver(post_save, sender=PoultryBatch)
def expand_protocol_on_batch_created(sender, instance, created, **kwargs):
    """Generates VACCINE_DUE / SANITARY_VOID_END AlertRule rows from the batch's house
    protocol lines (cahier des charges §4.6) as soon as a batch is created — covers both
    creation paths (`apps.protocols.views.OnboardingView` and
    `POST /api/batches/`) since it's a model-level signal, not view logic. See
    apps.protocols.services.expand_protocol_to_alert_rules."""
    if not created:
        return

    from apps.protocols.services import expand_protocol_to_alert_rules
    expand_protocol_to_alert_rules(instance)
