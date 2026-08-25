from rest_framework import serializers

from apps.finance.models import Expense, PurchaseOrder, Sale


class ExpenseSerializer(serializers.ModelSerializer):
    """GET/POST payload for /api/expenses/. `batch` is optional (null = farm-wide expense, not
    attributed to any batch — see Expense model docstring). `farm` is always taken from the
    requesting user, never accepted from the client."""

    class Meta:
        model = Expense
        fields = ['id', 'batch', 'category', 'amount', 'expense_date', 'supplier']
        read_only_fields = ['id']

    def create(self, validated_data):
        validated_data['farm'] = self.context['request'].user.farm
        return super().create(validated_data)


class SaleSerializer(serializers.ModelSerializer):
    """GET/POST payload for /api/sales/. `total_amount` is read-only — always recomputed
    server-side as `quantity * unit_price` (see Sale.save()); `farm`/`cashier` are always taken
    from the requesting user."""

    class Meta:
        model = Sale
        fields = ['id', 'batch', 'product_type', 'quantity', 'unit_price', 'total_amount', 'sale_date', 'customer']
        read_only_fields = ['id', 'total_amount']

    def create(self, validated_data):
        validated_data['farm'] = self.context['request'].user.farm
        validated_data['cashier'] = self.context['request'].user
        return super().create(validated_data)


class PurchaseOrderSerializer(serializers.ModelSerializer):
    """GET/POST/PATCH payload for /api/purchase-orders/ and /api/purchase-orders/{orderCode}/.
    `order_code` is server-generated (`PO-{farmId}-{seq}`). Transitioning `status` from anything
    else to RECEIVED via PATCH creates a matching StockMovement of type IN for `item` (see
    `update` below) — this side effect only fires on that specific transition, not on create with
    status already RECEIVED."""

    class Meta:
        model = PurchaseOrder
        fields = ['order_code', 'item', 'supplier', 'quantity', 'amount', 'order_date', 'status']
        read_only_fields = ['order_code', 'order_date']

    def create(self, validated_data):
        farm = self.context['request'].user.farm
        count = PurchaseOrder.objects.filter(farm=farm).count() + 1
        validated_data['order_code'] = f'PO-{farm.id}-{count:04d}'
        validated_data['farm'] = farm
        validated_data['cashier'] = self.context['request'].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        was_pending = instance.status != 'RECEIVED'
        instance = super().update(instance, validated_data)
        if was_pending and instance.status == 'RECEIVED':
            from apps.stock.models import MovementType, StockMovement
            StockMovement.objects.create(
                item=instance.item,
                movement_type=MovementType.IN,
                quantity=instance.quantity,
                movement_date=instance.order_date,
                supplier=instance.supplier,
            )
        return instance
