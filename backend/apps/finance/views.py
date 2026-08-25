from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema, inline_serializer
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import ADMIN, FARM_MANAGER, IsAdminOrCashier, IsAdminOrFarmManager
from apps.finance.calculations import expense_category_breakdown, finance_summary, finance_trend_direction
from apps.finance.models import Expense, PurchaseOrder, Sale
from apps.finance.serializers import ExpenseSerializer, PurchaseOrderSerializer, SaleSerializer

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
        page = int(request.query_params.get('page', 1))
        page_size = 20

        rows = []
        if type_filter in ('all', 'out'):
            for e in Expense.objects.filter(farm=farm):
                rows.append({
                    'id': f'EXP-{e.id}', 'date': e.expense_date, 'category': e.category,
                    'counterparty': e.supplier, 'amount': -float(e.amount), 'status': 'OUT',
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
    """GET/POST /api/expenses/ — history and creation of farm/batch expenses.
    Creation reserved to Admin / Farm Manager."""

    serializer_class = ExpenseSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminOrFarmManager()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return Expense.objects.filter(farm=self.request.user.farm)


class SaleListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/sales/ — history and creation of sales.
    Creation reserved to Admin / Cashier (section 8)."""

    serializer_class = SaleSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminOrCashier()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return Sale.objects.filter(farm=self.request.user.farm)


class PurchaseOrderListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/purchase-orders/ — history and creation of supplier purchase orders.
    Creation reserved to Admin / Cashier (section 8)."""

    serializer_class = PurchaseOrderSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAdminOrCashier()]
        return [IsAuthenticated()]

    def get_queryset(self):
        return PurchaseOrder.objects.filter(farm=self.request.user.farm)


class PurchaseOrderDetailView(generics.RetrieveUpdateAPIView):
    """PATCH /api/purchase-orders/{orderCode}/ — status transition to RECEIVED generates a StockMovement IN."""

    serializer_class = PurchaseOrderSerializer
    permission_classes = [IsAdminOrCashier]
    lookup_field = 'order_code'

    def get_queryset(self):
        return PurchaseOrder.objects.filter(farm=self.request.user.farm)
