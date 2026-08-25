from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.houses.models import PoultryHouse


@receiver(post_save, sender=PoultryHouse)
def seed_default_protocol_categories(sender, instance, created, **kwargs):
    """Seeds the 5 default ProtocolCategory rows (Alimentation/Température/Santé et
    soins/Vaccination/Nettoyage) for every newly-created house — UI scaffolding, not example
    farm content (the rows carry no protocol lines), so this doesn't violate the no-default-data
    rule. Fires for both house-creation paths (`POST /api/houses/` and
    `apps.protocols.views.OnboardingView`, which creates PoultryHouse directly rather than
    through PoultryHouseSerializer) since it's a model-level signal, not view logic."""
    if not created:
        return

    from apps.protocols.models import DEFAULT_PROTOCOL_CATEGORIES, ProtocolCategory

    ProtocolCategory.objects.bulk_create([
        ProtocolCategory(house=instance, label=cat['label'], icon=cat['icon'], sort_order=i)
        for i, cat in enumerate(DEFAULT_PROTOCOL_CATEGORIES)
    ])
