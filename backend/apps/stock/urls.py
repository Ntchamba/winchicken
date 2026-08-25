from django.urls import path

from apps.stock import views

urlpatterns = [
    path('farms/<int:farm_id>/stock-items/', views.FarmStockItemsView.as_view(), name='farm-stock-items'),
    path('stock-movements/', views.StockMovementListCreateView.as_view(), name='stock-movements'),
    path('vaccinations/', views.VaccinationListCreateView.as_view(), name='vaccinations'),
]
