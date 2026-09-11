from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.core import views

urlpatterns = [
    path('health/', views.HealthCheckView.as_view(), name='health'),
    path('farm/exists/', views.FarmExistsView.as_view(), name='farm-exists'),
    path('farm/create/', views.FarmCreateView.as_view(), name='farm-create'),
    path('farm/reset/', views.FarmResetView.as_view(), name='farm-reset'),
    path('farm/reset/request/', views.FarmResetRequestView.as_view(), name='farm-reset-request'),
    path('farm/reset/confirm/', views.FarmResetConfirmView.as_view(), name='farm-reset-confirm'),
    path('audit-log/', views.AuditLogListView.as_view(), name='audit-log'),
    path('auth/login/', views.LoginView.as_view(), name='auth-login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='auth-refresh'),
    path('auth/me/', views.MeView.as_view(), name='auth-me'),
    path('employees/', views.EmployeeListCreateView.as_view(), name='employee-list'),
    path('employees/import-xlsx/', views.EmployeeImportView.as_view(), name='employee-import'),
    path('employees/import-template.xlsx', views.EmployeeImportTemplateView.as_view(), name='employee-import-template'),
    path('employees/payroll/', views.EmployeePayrollListView.as_view(), name='employee-payroll-list'),
    path('employees/<int:pk>/', views.EmployeeDetailView.as_view(), name='employee-detail'),
    path('employees/<int:pk>/hourly-rate/', views.EmployeeHourlyRateView.as_view(), name='employee-hourly-rate'),
    path('farm/overview/', views.FarmOverviewView.as_view(), name='farm-overview'),
    path('contact/', views.ContactMessageView.as_view(), name='contact'),
    path('newsletter/', views.NewsletterSubscribeView.as_view(), name='newsletter'),
]
