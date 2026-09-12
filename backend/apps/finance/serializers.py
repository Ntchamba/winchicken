from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.core.permissions import ADMIN, FARM_MANAGER
from apps.finance.models import Expense, OrderStatus, PurchaseOrder, Sale, SalaryPayment, WorkHoursEntry


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
    `order_code` is server-generated (`PO-{farmId}-{seq}`). Transitioning `status` from PENDING
    to RECEIVED via PATCH creates a matching StockMovement of type IN for `item`, in the same
    transaction as the status update (see `update` below) — this side effect only fires on that
    specific transition, not on create with status already RECEIVED. A CANCELLED transition
    updates status only, no StockMovement. Once RECEIVED or CANCELLED an order is final — any
    further status change is rejected (2026-08-27, purchase-order task, Part B item 5: "no
    un-receiving, no un-cancelling — a mistake should be visible in the audit log," not silently
    reversible here).

    `itemName`/`itemCategory` (read-only) are display conveniences for the list screen, same
    reasoning as `EquipmentFaultSerializer.houseName` — the frontend shouldn't need a second
    round-trip to resolve `item` (an id) to a name.
    """

    itemName = serializers.CharField(source='item.name', read_only=True)
    itemCategory = serializers.CharField(source='item.category.kind', read_only=True)
    # Not a PurchaseOrder field — write-only input accepted on the RECEIVED-transition PATCH
    # only, recorded on the StockMovement that transition generates (2026-08-27, purchase-order
    # task, Part B item 3: "low-friction to add... add it"). Popped out of validated_data before
    # it ever reaches ModelSerializer's own create()/update(), which know nothing about it.
    supplierBatchNumber = serializers.CharField(
        write_only=True, required=False, allow_blank=True, default='',
        help_text='Optional — recorded on the StockMovement generated when this order is marked RECEIVED; ignored otherwise.',
    )

    class Meta:
        model = PurchaseOrder
        fields = [
            'order_code', 'item', 'itemName', 'itemCategory', 'supplier', 'quantity', 'amount',
            'order_date', 'status', 'supplierBatchNumber',
        ]
        read_only_fields = ['order_code', 'order_date']

    def validate(self, attrs):
        if self.instance and self.instance.status != OrderStatus.PENDING and 'status' in attrs \
                and attrs['status'] != self.instance.status:
            raise serializers.ValidationError({
                'status': "Cette commande est déjà finalisée (reçue ou annulée) — son statut ne peut plus être modifié.",
            })
        return attrs

    def create(self, validated_data):
        validated_data.pop('supplierBatchNumber', None)  # only meaningful at receiving time
        farm = self.context['request'].user.farm
        count = PurchaseOrder.objects.filter(farm=farm).count() + 1
        validated_data['order_code'] = f'PO-{farm.id}-{count:04d}'
        validated_data['farm'] = farm
        validated_data['cashier'] = self.context['request'].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        supplier_batch_number = validated_data.pop('supplierBatchNumber', '')
        was_pending = instance.status == OrderStatus.PENDING
        with transaction.atomic():
            instance = super().update(instance, validated_data)
            if was_pending and instance.status == OrderStatus.RECEIVED:
                from apps.stock.models import MovementType, StockMovement
                StockMovement.objects.create(
                    item=instance.item,
                    movement_type=MovementType.IN,
                    quantity=instance.quantity,
                    movement_date=timezone.localdate(),  # actual receiving date, not order_date
                    supplier=instance.supplier,
                    supplier_batch_number=supplier_batch_number,
                )
        return instance


class WorkHoursEntrySerializer(serializers.ModelSerializer):
    """GET/POST payload for /api/work-hours/ (Salaires module, 2026-08-27). `user` is optional on
    write — omit it to self-report (defaults to the requester); Admin/Farm Manager may set it to
    any employee on their farm to log/correct hours on that employee's behalf (this task's own
    Part D "hours-logging ownership model": self-report + admin override, see docs/deviations.md).
    Every other role attempting to set `user` to someone else is rejected here, not just hidden
    in the UI."""

    userName = serializers.CharField(source='user.name', read_only=True)

    class Meta:
        model = WorkHoursEntry
        fields = ['id', 'user', 'userName', 'date', 'hours_worked', 'note']
        read_only_fields = ['id']
        extra_kwargs = {'user': {'required': False}}

    def validate(self, attrs):
        request = self.context['request']
        target_user = attrs.get('user') or request.user
        if target_user.farm_id != request.user.farm_id:
            raise serializers.ValidationError({'user': "Cet employé n'appartient pas à votre ferme."})
        if target_user != request.user and request.user.role not in (ADMIN, FARM_MANAGER):
            raise serializers.ValidationError({'user': "Vous ne pouvez enregistrer des heures que pour vous-même."})
        attrs['user'] = target_user
        return attrs


class SalaryPaymentSerializer(serializers.ModelSerializer):
    """GET payload for /api/salary-payments/ — every field is system-computed (see
    apps.finance.services.calculate_salaries / apps.finance.views.SalaryPaymentPayView), so this
    serializer is read-only end to end; there is no direct create/update endpoint for this model,
    matching this task's own Part D wording ("generate/update a PENDING SalaryPayment", "Marquer
    comme payé action" — both dedicated actions, not a generic POST/PUT)."""

    employeeName = serializers.CharField(source='user.name', read_only=True)

    class Meta:
        model = SalaryPayment
        fields = [
            'id', 'user', 'employeeName', 'period_month', 'period_year',
            'total_hours', 'hourly_rate_snapshot', 'amount', 'status', 'paid_date',
        ]
        read_only_fields = fields
