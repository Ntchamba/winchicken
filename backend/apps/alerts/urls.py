from django.urls import path

from apps.alerts import views

urlpatterns = [
    path('alert-rules/', views.AlertRuleListCreateView.as_view(), name='alert-rules'),
    path('alerts/', views.AlertListView.as_view(), name='alerts'),
    path('alerts/mark-all-read/', views.AlertMarkAllReadView.as_view(), name='alerts-mark-all-read'),
    path('alerts/unread-count/', views.AlertUnreadCountView.as_view(), name='alerts-unread-count'),
    path('alerts/<int:pk>/mark-read/', views.AlertMarkReadView.as_view(), name='alert-mark-read'),
    path('sms-messages/', views.SmsMessageListView.as_view(), name='sms-messages'),
    path('notification-preferences/', views.NotificationPreferenceListView.as_view(), name='notification-preferences'),
    path('push-public-key/', views.PushPublicKeyView.as_view(), name='push-public-key'),
    path('push-subscriptions/', views.PushSubscriptionView.as_view(), name='push-subscriptions'),
]
