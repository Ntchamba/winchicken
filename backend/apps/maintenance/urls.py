from django.urls import path

from apps.maintenance import views

urlpatterns = [
    path('equipment-faults/', views.EquipmentFaultListCreateView.as_view(), name='equipment-faults'),
    path('unusual-cases/', views.UnusualCaseListCreateView.as_view(), name='unusual-cases'),
]
