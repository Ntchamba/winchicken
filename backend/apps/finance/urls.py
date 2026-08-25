from django.urls import path

from apps.finance import views

urlpatterns = [
    path('finance/summary/', views.FinanceSummaryView.as_view(), name='finance-summary'),
    path('finance/expense-categories/', views.FinanceExpenseCategoriesView.as_view(), name='finance-expense-categories'),
    path('finance/transactions/', views.FinanceTransactionsView.as_view(), name='finance-transactions'),
    path('expenses/', views.ExpenseListCreateView.as_view(), name='expenses'),
    path('sales/', views.SaleListCreateView.as_view(), name='sales'),
    path('purchase-orders/', views.PurchaseOrderListCreateView.as_view(), name='purchase-orders'),
    path('purchase-orders/<str:order_code>/', views.PurchaseOrderDetailView.as_view(), name='purchase-order-detail'),
]
