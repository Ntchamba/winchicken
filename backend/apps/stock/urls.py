from django.urls import path

from apps.stock import views

urlpatterns = [
    path('farms/<int:farm_id>/stock-items/', views.FarmStockItemsView.as_view(), name='farm-stock-items'),
    path('farms/<int:farm_id>/stock-categories/', views.FarmStockCategoriesView.as_view(), name='farm-stock-categories'),
    path('stock-categories/<int:pk>/', views.StockCategoryDetailView.as_view(), name='stock-category-detail'),
    path('farms/<int:farm_id>/suppliers/', views.FarmSuppliersView.as_view(), name='farm-suppliers'),
    path('suppliers/<int:pk>/', views.SupplierDetailView.as_view(), name='supplier-detail'),
    path('farms/<int:farm_id>/stock-evolution/', views.FarmStockEvolutionView.as_view(), name='farm-stock-evolution'),
    path('stock-items/low-count/', views.StockItemsLowCountView.as_view(), name='stock-items-low-count'),
    path('stock-items/<str:item_code>/coverage/', views.StockItemCoverageView.as_view(), name='stock-item-coverage'),
    path('stock-movements/', views.StockMovementListCreateView.as_view(), name='stock-movements'),
    path('vaccinations/', views.VaccinationListCreateView.as_view(), name='vaccinations'),
]
