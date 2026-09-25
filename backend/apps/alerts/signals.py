from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.batches.models import DailyLog
from apps.finance.models import Expense, PurchaseOrder, Sale
from apps.maintenance.models import EquipmentFault, UnusualCase
from apps.stock.models import MovementType, StockMovement


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


# --- Desktop-notification fan-out (2026-08-31) --------------------------------------
# Every "something changed" the user asked to be told about funnels through
# `apps.alerts.notify.notify_farm`, which queues a Web Push on transaction commit. Each
# handler stays cheap: one `notify_farm` call, no extra work when push is disabled (the
# helper returns immediately). `tag` lets the service worker collapse repeats of the same
# event instead of stacking them.

def _notify(farm_id, *, title, body, url='/', tag=None):
    from apps.alerts.notify import notify_farm
    notify_farm(farm_id, title=title, body=body, url=url, tag=tag)


@receiver(post_save, sender='alerts.Alert')
def push_on_alert(sender, instance, created, **kwargs):
    if not created:
        return
    from apps.alerts.services import alert_display_message

    rule = instance.rule
    _notify(
        rule.farm_id,
        title='Nouvelle alerte',
        body=alert_display_message(instance),
        url='/dashboard/alerts',
        tag=f'alert-{instance.pk}',
    )


@receiver(post_save, sender=StockMovement)
def push_on_stock_movement(sender, instance, created, **kwargs):
    if not created:
        return
    item = instance.item
    verb = 'Entrée' if instance.movement_type == MovementType.IN else 'Sortie'
    _notify(
        item.farm_id,
        title=f'{verb} de stock · {item.name}',
        body=f'{instance.quantity:g} {item.unit} — {instance.movement_date}',
        url='/dashboard/stock',
        tag=f'stockmvt-{instance.pk}',
    )


@receiver(post_save, sender=Expense)
def push_on_expense(sender, instance, created, **kwargs):
    if not created:
        return
    _notify(
        instance.farm_id,
        title='Nouvelle dépense',
        body=f'{instance.get_category_display()} · {instance.amount}',
        url='/dashboard/finances',
        tag=f'expense-{instance.pk}',
    )


@receiver(post_save, sender=Sale)
def push_on_sale(sender, instance, created, **kwargs):
    if not created:
        return
    _notify(
        instance.farm_id,
        title='Nouvelle vente',
        body=f'{instance.get_product_type_display()} · {instance.total_amount}',
        url='/dashboard/finances',
        tag=f'sale-{instance.pk}',
    )


@receiver(post_save, sender=PurchaseOrder)
def push_on_purchase_order(sender, instance, created, **kwargs):
    if created:
        title, tag = 'Bon de commande créé', f'po-new-{instance.pk}'
    elif instance.status == 'RECEIVED':
        title, tag = 'Bon de commande reçu', f'po-received-{instance.pk}'
    else:
        return
    _notify(
        instance.farm_id,
        title=title,
        body=f'{instance.quantity:g} · {instance.amount}',
        url='/dashboard/purchase-orders',
        tag=tag,
    )


@receiver(post_save, sender=UnusualCase)
def push_on_unusual_case(sender, instance, created, **kwargs):
    if not created:
        return
    farm_id = instance.batch.house.farm_id
    _notify(
        farm_id,
        title='Cas inhabituel signalé',
        body=instance.case_description[:120],
        url='/dashboard/houses',
        tag=f'case-{instance.case_code}',
    )


@receiver(post_save, sender=EquipmentFault)
def push_on_equipment_fault(sender, instance, created, **kwargs):
    if not created:
        return
    farm_id = instance.house.farm_id
    _notify(
        farm_id,
        title='Panne d’équipement signalée',
        body=instance.fault_description[:120],
        url='/dashboard/houses',
        tag=f'fault-{instance.fault_code}',
    )
