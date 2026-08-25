from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.batches.models import DailyLog
from apps.stock.models import StockMovement


@receiver(post_save, sender=StockMovement)
def on_stock_movement_saved(sender, instance, **kwargs):
    from apps.alerts.services import check_low_stock
    check_low_stock(instance.item)


@receiver(post_save, sender=DailyLog)
def on_daily_log_saved(sender, instance, created, **kwargs):
    if not created:
        return
    from apps.alerts.services import check_consumption_deviation
    check_consumption_deviation(instance)
