from django.urls import path

from apps.houses import views

urlpatterns = [
    path('houses/', views.HouseListCreateView.as_view(), name='house-list'),
    path('houses/<str:house_code>/', views.HouseDetailView.as_view(), name='house-detail'),
    path('houses/<str:house_code>/protocol/', views.HouseProtocolView.as_view(), name='house-protocol'),
    path('houses/<str:house_code>/protocol-categories/', views.ProtocolCategoryListCreateView.as_view(), name='house-protocol-categories'),
    path('houses/<str:house_code>/protocol-categories/<int:pk>/', views.ProtocolCategoryDetailView.as_view(), name='house-protocol-category-detail'),
]
