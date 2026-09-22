from django.urls import path

from apps.finance import views

urlpatterns = [
    path('finance/summary/', views.FinanceSummaryView.as_view(), name='finance-summary'),
    path('finance/expense-categories/', views.FinanceExpenseCategoriesView.as_view(), name='finance-expense-categories'),
    path('finance/transactions/', views.FinanceTransactionsView.as_view(), name='finance-transactions'),
    path('expenses/', views.ExpenseListCreateView.as_view(), name='expenses'),
    path('sales/', views.SaleListCreateView.as_view(), name='sales'),
    path('purchase-orders/', views.PurchaseOrderListCreateView.as_view(), name='purchase-orders'),
    path('purchase-orders/pending-count/', views.PurchaseOrderPendingCountView.as_view(), name='purchase-orders-pending-count'),
    path('purchase-orders/<str:order_code>/', views.PurchaseOrderDetailView.as_view(), name='purchase-order-detail'),
    path('finance/sales-evolution/', views.SalesEvolutionView.as_view(), name='finance-sales-evolution'),
    path('finance/purchases-evolution/', views.PurchasesEvolutionView.as_view(), name='finance-purchases-evolution'),
    path('work-hours/', views.WorkHoursEntryListCreateView.as_view(), name='work-hours'),
    path('salary-payments/', views.SalaryPaymentListView.as_view(), name='salary-payments'),
    path('salary-payments/calculate/', views.SalaryCalculateView.as_view(), name='salary-payments-calculate'),
    path('salary-payments/<int:pk>/pay/', views.SalaryPaymentPayView.as_view(), name='salary-payment-pay'),
]
