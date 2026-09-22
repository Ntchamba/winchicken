from django.urls import path

from apps.maintenance import views

urlpatterns = [
    path('equipment-faults/', views.EquipmentFaultListCreateView.as_view(), name='equipment-faults'),
    path('equipment-faults/<str:fault_code>/', views.EquipmentFaultDetailView.as_view(), name='equipment-fault-detail'),
    path('unusual-cases/', views.UnusualCaseListCreateView.as_view(), name='unusual-cases'),
    path('unusual-cases/<str:case_code>/', views.UnusualCaseDetailView.as_view(), name='unusual-case-detail'),
]
