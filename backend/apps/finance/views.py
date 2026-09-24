import datetime

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import ADMIN, FARM_MANAGER, IsAdminOrCashier, IsAdminOrFarmManager, IsAdminOrFarmManagerOrCashier
from apps.core.services import record_audit_log
from apps.finance.calculations import (
    _ITEM_CATEGORY_TO_EXPENSE_CATEGORY, expense_category_breakdown, finance_summary, finance_trend_direction,
    purchases_evolution, sales_evolution, series_trend,
)
from apps.finance.models import (
    Expense, ExpenseCategory, OrderStatus, PurchaseOrder, Sale, SalaryPayment, SalaryPaymentStatus, WorkHoursEntry,
)
from apps.finance.serializers import (
    ExpenseSerializer, PurchaseOrderSerializer, SaleSerializer, SalaryPaymentSerializer, WorkHoursEntrySerializer,
)
from apps.finance.services import calculate_salaries

_RANGE_PARAM = OpenApiParameter(
    name='range', type=str, required=False,
    description='"6m" (default) or "1y" — window size for the aggregation.',
)


@extend_schema(
    parameters=[_RANGE_PARAM],
    responses=inline_serializer('FinanceSummaryResponse', {
        'access': serializers.ChoiceField(choices=['full', 'restricted']),
        'range': serializers.CharField(),
        'months': inline_serializer('FinanceSummaryMonth', {
            'month': serializers.CharField(), 'revenue': serializers.FloatField(), 'expenses': serializers.FloatField(),
        }, many=True, required=False),
        'cashOnHand': serializers.FloatField(required=False),
        'pendingPayables': serializers.FloatField(required=False),
        'roiForecastPct': serializers.FloatField(allow_null=True, required=False, help_text='null ("not available") until at least one EQUIPMENT purchase has been RECEIVED.'),
        'revenueTrend': serializers.ChoiceField(choices=['up', 'down', 'flat'], required=False),
        'expenseTrend': serializers.ChoiceField(choices=['up', 'down', 'flat'], required=False),
    }),
    examples=[
        OpenApiExample('Full access (Admin / Farm Manager)', value={
            'access': 'full', 'range': '6m',
            'months': [{'month': '2026-03', 'revenue': 812000, 'expenses': 610000}],
            'cashOnHand': 245600, 'pendingPayables': 18420.5, 'roiForecastPct': None,
        }, response_only=True),
        OpenApiExample('Restricted access (every other role)', value={
            'access': 'restricted', 'range': '6m', 'revenueTrend': 'up', 'expenseTrend': 'flat',
        }, response_only=True),
    ],
)
class FinanceSummaryView(APIView):
    """GET /api/finance/summary/?range=6m|1y — open to every authenticated role (Finance access
    matrix, winchicken-spec-implementation-detaillee.docx sections 4.3/8): Admin / Farm Manager
    get the full monthly trend plus cash-on-hand, pending payables and ROI forecast
    (`access: "full"`, implementation-detail spec 11.2); every other role gets direction-only
    trend with no monetary figures (`access: "restricted"`). `FinanceExpenseCategoriesView` and
    `FinanceTransactionsView` below stay Admin/Farm-Manager-only for the exact-amount detail."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        range_param = request.query_params.get('range', '6m')
        farm = request.user.farm
        if request.user.role in (ADMIN, FARM_MANAGER):
            return Response({'access': 'full', **finance_summary(farm, range_param)})
        return Response({'access': 'restricted', 'range': range_param, **finance_trend_direction(farm, range_param)})


@extend_schema(
    parameters=[_RANGE_PARAM],
    responses=inline_serializer('ExpenseCategoriesResponse', {
        'range': serializers.CharField(),
        'categories': inline_serializer('ExpenseCategoryShare', {
            'category': serializers.CharField(), 'amountPct': serializers.FloatField(),
        }, many=True),
    }),
)
class FinanceExpenseCategoriesView(APIView):
    """GET /api/finance/expense-categories/?range=6m|1y — expense breakdown by category as a
    percentage of total expenses over the window, for the Finance view's donut chart
    (implementation-detail spec 11.3). Reserved to Admin / Farm Manager."""

    permission_classes = [IsAdminOrFarmManager]

    def get(self, request):
        range_param = request.query_params.get('range', '6m')
        return Response(expense_category_breakdown(request.user.farm, range_param))


@extend_schema(
    parameters=[
        OpenApiParameter(name='type', type=str, required=False, description='"in" (sales), "out" (expenses) or "all" (default).'),
        OpenApiParameter(name='page', type=int, required=False, description='1-indexed page number; page size is fixed at 20.'),
    ],
    responses=inline_serializer('FinanceTransactionsResponse', {
        'count': serializers.IntegerField(),
        'page': serializers.IntegerField(),
        'pageSize': serializers.IntegerField(),
        'results': inline_serializer('FinanceTransactionRow', {
            'id': serializers.CharField(help_text='"EXP-{id}" or "SALE-{id}" — not a real primary key, just a display id.'),
            'date': serializers.DateField(),
            'category': serializers.CharField(),
            'counterparty': serializers.CharField(),
            'amount': serializers.FloatField(help_text='Negative for expenses (OUT), positive for sales (IN).'),
            'status': serializers.CharField(help_text='"IN" or "OUT".'),
        }, many=True),
    }),
)
class FinanceTransactionsView(generics.ListAPIView):
    """GET /api/finance/transactions/ — Expense and Sale rows merged into one reverse-chronological,
    manually paginated list (this view sets `pagination_class = None` and paginates by hand, unlike
    every other list endpoint which uses the project-wide PageNumberPagination), filterable by
    ?type=in|out|all. Reserved to Admin / Farm Manager."""

    permission_classes = [IsAdminOrFarmManager]
    pagination_class = None

    def list(self, request, *args, **kwargs):
        farm = request.user.farm
        type_filter = request.query_params.get('type', 'all')
        raw_page = request.query_params.get('page', '1')
        if not raw_page.isdigit() or int(raw_page) < 1:
            return Response({'detail': f'Page invalide : {raw_page}.'}, status=status.HTTP_400_BAD_REQUEST)
        page = int(raw_page)
        page_size = 20

        rows = []
        if type_filter in ('all', 'out'):
            for e in Expense.objects.filter(farm=farm):
                rows.append({
                    'id': f'EXP-{e.id}', 'date': e.expense_date, 'category': e.category,
                    'counterparty': e.supplier, 'amount': -float(e.amount), 'status': 'OUT',
                })
            # RECEIVED purchase orders are money out too — the cash position subtracts them, so
            # the ledger has to list them or its rows never add up to it. Mapped to an expense
            # category the way the Achats breakdown does.
            for o in PurchaseOrder.objects.filter(farm=farm, status=OrderStatus.RECEIVED).select_related('item__category'):
                rows.append({
                    'id': f'PO-{o.order_code}', 'date': o.order_date,
                    'category': _ITEM_CATEGORY_TO_EXPENSE_CATEGORY.get(o.item.category.kind, ExpenseCategory.MISC),
                    'counterparty': o.supplier, 'amount': -float(o.amount), 'status': 'OUT',
                })
        if type_filter in ('all', 'in'):
            for s in Sale.objects.filter(farm=farm):
                rows.append({
                    'id': f'SALE-{s.id}', 'date': s.sale_date, 'category': s.product_type,
                    'counterparty': s.customer, 'amount': float(s.total_amount), 'status': 'IN',
                })
        rows.sort(key=lambda r: r['date'], reverse=True)

        total = len(rows)
        start = (page - 1) * page_size
        paged = rows[start:start + page_size]
        return Response({'count': total, 'page': page, 'pageSize': page_size, 'results': paged})


class ExpenseListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/expenses/ — history and creation of farm/batch expenses. Creation reserved
    to Admin / Farm Manager / Cashier — widened 2026-08-27 (Finances restructure, Part C) to add
    Cashier, so the new "Enregistrer une dépense" action on `/dashboard/cashier` can use this
    same endpoint rather than a duplicate one; Admin/Farm Manager's pre-existing access is
    unchanged, only added to, not narrowed."""

    serializer_class = ExpenseSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminOrFarmManagerOrCashier()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return Expense.objects.filter(farm=self.request.user.farm)

    def perform_create(self, serializer):
        # farm comes from ExpenseSerializer.create() itself (request context) — not passed here.
        expense = serializer.save()
        record_audit_log(self.request.user, 'expense.created', f'{expense.get_category_display()} · {expense.amount}')


class SaleListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/sales/ — history and creation of sales.
    Creation reserved to Admin / Cashier (section 8)."""

    serializer_class = SaleSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminOrCashier()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = Sale.objects.filter(farm=self.request.user.farm)
        # ?sale_date=YYYY-MM-DD — the cashier's "Ventes du jour": summing today's rows out of page 1
        # of every sale left the total short from the 21st sale of the day.
        raw_date = self.request.query_params.get('sale_date')
        if raw_date:
            try:
                sale_date = datetime.date.fromisoformat(raw_date)
            except ValueError:
                raise serializers.ValidationError({'sale_date': f'Date invalide : {raw_date} (attendu AAAA-MM-JJ).'})
            qs = qs.filter(sale_date=sale_date)
        return qs

    def perform_create(self, serializer):
        # farm/cashier come from SaleSerializer.create() itself (request context) — not passed here.
        sale = serializer.save()
        record_audit_log(self.request.user, 'sale.created', f'{sale.get_product_type_display()} · {sale.total_amount}')


class PurchaseOrderListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/purchase-orders/ — history and creation of supplier purchase orders.
    Creation reserved to Admin / Farm Manager / Cashier (2026-08-27, purchase-order task —
    widened from Admin/Cashier only, which was missing Farm Manager despite the task's own
    role list; a new `IsAdminOrFarmManagerOrCashier` was added rather than widening the
    existing `IsAdminOrCashier` in place, since that one is also used by `SaleListCreateView`,
    explicitly out of this task's scope). `?status=`/`?category=` filter the list server-side
    (category filters by the related `StockItem.category`) — same query-param-filtering
    convention as `EquipmentFaultListCreateView`/`UnusualCaseListCreateView`."""

    serializer_class = PurchaseOrderSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminOrFarmManagerOrCashier()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = PurchaseOrder.objects.filter(farm=self.request.user.farm).select_related('item')
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(item__category__kind=category)
        return qs

    def perform_create(self, serializer):
        # farm/cashier/order_code come from PurchaseOrderSerializer.create() itself — not passed here.
        order = serializer.save()
        record_audit_log(self.request.user, 'purchase_order.created', f'{order.order_code} · {order.supplier}')


class PurchaseOrderDetailView(generics.RetrieveUpdateAPIView):
    """PATCH /api/purchase-orders/{orderCode}/ — status transition to RECEIVED generates a
    StockMovement IN (see `PurchaseOrderSerializer.update`, wrapped in one transaction); a
    transition to CANCELLED just updates status, no StockMovement. Once RECEIVED or CANCELLED
    an order is final — the serializer itself rejects any further status change (2026-08-27,
    purchase-order task, Part B item 5) — logged to the audit trail either way, since that's
    this task's own stated substitute for "no un-receiving/un-cancelling."."""

    serializer_class = PurchaseOrderSerializer
    permission_classes = [IsAdminOrFarmManagerOrCashier]
    lookup_field = 'order_code'

    def get_queryset(self):
        return PurchaseOrder.objects.filter(farm=self.request.user.farm)

    def perform_update(self, serializer):
        previous_status = serializer.instance.status
        order = serializer.save()
        if order.status != previous_status and order.status == 'RECEIVED':
            record_audit_log(self.request.user, 'purchase_order.received', f'{order.order_code} · {order.supplier}')
        elif order.status != previous_status and order.status == 'CANCELLED':
            record_audit_log(self.request.user, 'purchase_order.cancelled', f'{order.order_code} · {order.supplier}')


class PurchaseOrderPendingCountView(APIView):
    """GET /api/purchase-orders/pending-count/ — sidebar Finance badge. `IsAdminOrFarmManager`,
    not the broader `IsAdminOrFarmManagerOrCashier` used for PO create/update above — this
    reuses the same Finance-access role set as FinanceSummaryView's `access: "full"` branch
    (deviation #28), so the count never leaks to a role that can't see full Finance figures
    either."""

    permission_classes = [IsAdminOrFarmManager]

    def get(self, request):
        count = PurchaseOrder.objects.filter(farm=request.user.farm, status='PENDING').count()
        return Response({'count': count})


_PERIOD_PARAM = OpenApiParameter(
    name='period', type=str, required=False,
    description='"week" (8 weeks), "month" (12 months, default) or "year" (5 years).',
)


class SalesEvolutionView(APIView):
    """GET /api/finance/sales-evolution/?period=week|month|year — "Ventes" section (2026-08-27,
    Finances restructure Part B): bucketed revenue series + period totals/breakdown. Same
    Admin/Farm-Manager-full vs. everyone-else-restricted split as `FinanceSummaryView` (direction
    only, no amounts) — Caissier keeps full detail on their *own* recorded sales via
    `/dashboard/cashier`/`GET /api/sales/` regardless (unchanged), this is the farm-wide
    aggregate view specifically."""

    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=[_PERIOD_PARAM])
    def get(self, request):
        period = request.query_params.get('period', 'month')
        farm = request.user.farm
        if request.user.role in (ADMIN, FARM_MANAGER):
            return Response({'access': 'full', **sales_evolution(farm, period)})
        return Response({'access': 'restricted', 'period': period, 'trend': series_trend(sales_evolution(farm, period)['series'])})


class PurchasesEvolutionView(APIView):
    """GET /api/finance/purchases-evolution/?period=week|month|year — "Achats" section
    (2026-08-27, Finances restructure Part C): read-only aggregation of RECEIVED PurchaseOrder +
    Expense rows (see apps.finance.calculations.purchases_evolution) — no data entry here. Same
    access split as SalesEvolutionView above."""

    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=[_PERIOD_PARAM])
    def get(self, request):
        period = request.query_params.get('period', 'month')
        farm = request.user.farm
        if request.user.role in (ADMIN, FARM_MANAGER):
            return Response({'access': 'full', **purchases_evolution(farm, period)})
        return Response({'access': 'restricted', 'period': period, 'trend': series_trend(purchases_evolution(farm, period)['series'])})


class WorkHoursEntryListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/work-hours/ — Salaires module (2026-08-27, Part D). Any authenticated user
    can log their own hours (self-report); Admin/Farm Manager can also log/correct hours for any
    employee on the farm (see WorkHoursEntrySerializer.validate for the enforcement — this task's
    "hours-logging ownership model," see docs/deviations.md). Listing: Admin/Farm Manager see
    every employee's entries (needed to review before calculating salaries); every other role
    sees only their own."""

    serializer_class = WorkHoursEntrySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = WorkHoursEntry.objects.filter(user__farm=self.request.user.farm).select_related('user')
        if self.request.user.role not in (ADMIN, FARM_MANAGER):
            qs = qs.filter(user=self.request.user)
        return qs


class SalaryPaymentListView(generics.ListAPIView):
    """GET /api/salary-payments/ — Admin/Farm Manager only. Unlike Ventes/Achats/Globale, the
    entire Salaires section is hidden from every other role — no restricted summary view (this
    task's own Part D item 4: salary data is sensitive, "hidden entirely from everyone else,"
    enforced here server-side, not just left off the sidebar)."""

    serializer_class = SalaryPaymentSerializer
    permission_classes = [IsAdminOrFarmManager]

    def get_queryset(self):
        return SalaryPayment.objects.filter(farm=self.request.user.farm).select_related('user')


class SalaryCalculateView(APIView):
    """POST /api/salary-payments/calculate/ — {month, year} (both optional, default to the
    current month/year). On-demand monthly salary calculation (see
    apps.finance.services.calculate_salaries for why on-demand, not scheduled, and why an
    already-PAID payment for the period is never touched)."""

    permission_classes = [IsAdminOrFarmManager]

    def post(self, request):
        today = timezone.localdate()
        try:
            month = int(request.data.get('month', today.month))
            year = int(request.data.get('year', today.year))
        except (TypeError, ValueError):
            return Response({'detail': 'month/year doivent être des entiers.'}, status=status.HTTP_400_BAD_REQUEST)
        payments = calculate_salaries(request.user.farm, month, year)
        return Response(SalaryPaymentSerializer(payments, many=True).data)


class SalaryPaymentPayView(APIView):
    """POST /api/salary-payments/{id}/pay/ — marks one SalaryPayment PAID, stamps `paid_date`,
    and creates the matching `Expense` (category=LABOR, batch=null, amount=payment.amount,
    expense_date=paid_date, supplier=employee name) — all in one transaction (this task's own
    rule). This is what feeds "Main-d'œuvre" into the Achats/Globale expense breakdowns. Once
    PAID an payment is final, matching PurchaseOrder's own finality precedent in this codebase —
    a second call is rejected, not silently re-applied."""

    permission_classes = [IsAdminOrFarmManager]

    def post(self, request, pk):
        payment = get_object_or_404(SalaryPayment, pk=pk, farm=request.user.farm)
        if payment.status == SalaryPaymentStatus.PAID:
            return Response({'detail': 'Ce paiement est déjà marqué comme payé.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            payment.status = SalaryPaymentStatus.PAID
            payment.paid_date = timezone.localdate()
            payment.save(update_fields=['status', 'paid_date'])
            Expense.objects.create(
                farm=request.user.farm, category=ExpenseCategory.LABOR, amount=payment.amount,
                batch=None, expense_date=payment.paid_date, supplier=payment.user.name,
            )
        record_audit_log(
            request.user, 'salary_payment.paid',
            f'{payment.user.name} · {payment.period_month}/{payment.period_year} · {payment.amount}',
        )
        return Response(SalaryPaymentSerializer(payment).data)
