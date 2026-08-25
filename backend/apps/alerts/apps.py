from django.apps import AppConfig


class AlertsConfig(AppConfig):
    name = 'apps.alerts'

    def ready(self):
        from apps.alerts import signals  # noqa: F401
