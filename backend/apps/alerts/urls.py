from django.urls import path

from apps.alerts import views

urlpatterns = [
    path('alert-rules/', views.AlertRuleListCreateView.as_view(), name='alert-rules'),
    path('alerts/', views.AlertListView.as_view(), name='alerts'),
    path('alerts/<int:pk>/', views.AlertDetailView.as_view(), name='alert-detail'),
    path('alerts/sms/webhook/', views.SmsDeliveryWebhookView.as_view(), name='sms-delivery-webhook'),
    path('sms-messages/', views.SmsMessageListView.as_view(), name='sms-messages'),
    path('notification-preferences/', views.NotificationPreferenceListView.as_view(), name='notification-preferences'),
]
