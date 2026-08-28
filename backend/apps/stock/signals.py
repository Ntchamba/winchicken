from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.core.models import Farm


@receiver(post_save, sender=Farm)
def seed_default_stock_categories(sender, instance, created, **kwargs):
    """Seeds the four default StockCategory rows (Aliment/Vétérinaire/Équipement/Litière) for
    every newly-created Farm — UI scaffolding, not example farm content (the rows carry no
    items), so this doesn't violate the no-default-data rule. Mirrors
    `apps.houses.signals.seed_default_protocol_categories`."""
    if not created:
        return

    from apps.stock.models import DEFAULT_STOCK_CATEGORIES, StockCategory

    StockCategory.objects.bulk_create([
        StockCategory(farm=instance, label=cat['label'], icon=cat['icon'], kind=cat['kind'], sort_order=i)
        for i, cat in enumerate(DEFAULT_STOCK_CATEGORIES)
    ])
