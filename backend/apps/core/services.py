def is_farm_configured(farm):
    """True once the farm has >=1 PoultryHouse with >=1 ProtocolTemplate line AND >=1 StockItem.

    The employees onboarding step is deliberately excluded from this condition (cahier des
    charges 5.3) — it is skippable without blocking dashboard access.
    """
    from apps.houses.models import PoultryHouse
    from apps.stock.models import StockItem

    has_configured_house = PoultryHouse.objects.filter(
        farm=farm, protocol_lines__isnull=False
    ).distinct().exists()
    has_stock_item = StockItem.objects.filter(farm=farm).exists()
    return has_configured_house and has_stock_item
