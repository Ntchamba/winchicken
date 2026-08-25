from django.urls import path

from apps.alerts import views

urlpatterns = [
    path('alert-rules/', views.AlertRuleListCreateView.as_view(), name='alert-rules'),
    path('alerts/', views.AlertListView.as_view(), name='alerts'),
    path('sms-messages/', views.SmsMessageListView.as_view(), name='sms-messages'),
    path('notification-preferences/', views.NotificationPreferenceListView.as_view(), name='notification-preferences'),
]
