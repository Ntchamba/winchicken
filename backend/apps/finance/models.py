from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.batches.models import PoultryBatch
from apps.core.models import Farm
from apps.stock.models import StockItem


class ExpenseCategory(models.TextChoices):
    """FEED / VETERINARY / MISC are treated as *variable* costs and DEPRECIATION / LABOR as
    *fixed* costs by apps.batches.calculations.build_closing_report and
    apps.finance.calculations (see the `variable_categories` / `fixed_categories` lists there) —
    this variable/fixed split is a code convention, not a field on this model."""

    FEED = 'FEED', 'Feed'
    VETERINARY = 'VETERINARY', 'Veterinary'
    MISC = 'MISC', 'Misc'
    DEPRECIATION = 'DEPRECIATION', 'Depreciation'
    LABOR = 'LABOR', 'Labor'


class Expense(models.Model):
    """A farm or batch-level cost. `batch` is nullable — farm-wide expenses (e.g. general
    equipment depreciation) are not attributed to any single batch and are excluded from
    per-batch calculations (mortality/FCR/margin) but included in farm-wide ones
    (apps.finance.calculations.monthly_summary, cash_on_hand)."""

    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='expenses')
    batch = models.ForeignKey(PoultryBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    category = models.CharField(max_length=16, choices=ExpenseCategory.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    expense_date = models.DateField()
    supplier = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-expense_date']

    def __str__(self):
        return f'{self.category} · {self.amount}'


class ProductType(models.TextChoices):
    BIRD = 'BIRD', 'Bird'
    EGG = 'EGG', 'Egg'
    CULL = 'CULL', 'Cull'
    MANURE = 'MANURE', 'Manure'


class Sale(models.Model):
    """A recorded sale (birds, eggs, culls or manure). `total_amount` is always recomputed from
    `quantity * unit_price` on save (see `save()` below) — never trusted from client input, even
    if submitted."""

    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='sales')
    batch = models.ForeignKey(PoultryBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='sales')
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='recorded_sales'
    )
    product_type = models.CharField(max_length=16, choices=ProductType.choices)
    quantity = models.FloatField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    sale_date = models.DateField()
    customer = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-sale_date']

    def save(self, *args, **kwargs):
        # quantity is a float, unit_price a Decimal — Python won't multiply them directly.
        self.total_amount = Decimal(str(self.quantity)) * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.product_type} · {self.total_amount}'


class OrderStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    RECEIVED = 'RECEIVED', 'Received'
    CANCELLED = 'CANCELLED', 'Cancelled'


class PurchaseOrder(models.Model):
    """Supplier restocking order, distinct from a Sale. Transitioning `status` to RECEIVED via
    `PATCH /api/purchase-orders/{orderCode}/` generates a StockMovement of type IN for `item`
    (see apps.finance.serializers.PurchaseOrderSerializer.update) — that PATCH endpoint is an
    addition beyond the cahier des charges' documented endpoint list (section 10 only lists
    GET/POST on /api/purchase-orders/), added specifically to implement this rule.
    `RECEIVED` PurchaseOrder rows in the EQUIPMENT item category are also the only proxy this
    codebase has for "investment" in `apps.finance.calculations.roi_forecast_pct` — the schema
    has no dedicated investment/capital-expenditure table."""

    order_code = models.CharField(max_length=32, primary_key=True)
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='purchase_orders')
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='placed_orders'
    )
    item = models.ForeignKey(StockItem, on_delete=models.CASCADE, related_name='purchase_orders')
    supplier = models.CharField(max_length=255, blank=True)
    quantity = models.FloatField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    order_date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=16, choices=OrderStatus.choices, default=OrderStatus.PENDING)

    class Meta:
        ordering = ['-order_date']

    def __str__(self):
        return self.order_code


class WorkHoursEntry(models.Model):
    """One day's worked hours for one employee (Salaires module, 2026-08-27). Self-reported by
    the employee (`user` == the logged-in requester) or entered/corrected on their behalf by
    Admin/Farm Manager (see apps.finance.views.WorkHoursEntryListCreateView) — no farm FK here
    directly, `user.farm` is the scoping (matches how `PurchaseOrder.cashier`/`Sale.cashier`
    don't duplicate farm scoping through the user either)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='work_hours_entries')
    date = models.DateField()
    hours_worked = models.DecimalField(max_digits=5, decimal_places=2)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f'{self.user_id} · {self.date} · {self.hours_worked}h'


class SalaryPaymentStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    PAID = 'PAID', 'Paid'


class SalaryPayment(models.Model):
    """One employee's computed pay for one calendar month (Salaires module, 2026-08-27).
    `total_hours`/`hourly_rate_snapshot` are snapshots taken at calculation time — a later change
    to `User.hourly_rate`, or to the underlying `WorkHoursEntry` rows after this payment is
    marked PAID, never retroactively changes an already-PAID `amount` (recalculating only ever
    touches a still-PENDING row for that period, see apps.finance.services.calculate_salaries).
    Marking PAID also creates a matching `Expense` (category=LABOR, batch=null) in the same
    transaction — see apps.finance.views.SalaryPaymentPayView — which is what feeds "Main-d'œuvre"
    into the Achats/Globale expense breakdowns.
    """

    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='salary_payments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='salary_payments')
    period_month = models.PositiveSmallIntegerField()
    period_year = models.PositiveSmallIntegerField()
    total_hours = models.DecimalField(max_digits=7, decimal_places=2)
    hourly_rate_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=16, choices=SalaryPaymentStatus.choices, default=SalaryPaymentStatus.PENDING)
    paid_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period_year', '-period_month']
        constraints = [
            models.UniqueConstraint(fields=['user', 'period_month', 'period_year'], name='one_salary_payment_per_user_per_period'),
        ]

    def __str__(self):
        return f'{self.user_id} · {self.period_month}/{self.period_year} · {self.amount}'
