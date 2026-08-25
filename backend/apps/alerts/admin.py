from django.contrib import admin

from apps.alerts.models import Alert, AlertRule, NotificationPreference, SmsMessage

admin.site.register(AlertRule)
admin.site.register(Alert)
admin.site.register(SmsMessage)
admin.site.register(NotificationPreference)
