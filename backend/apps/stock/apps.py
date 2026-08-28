from django.apps import AppConfig


class StockConfig(AppConfig):
    name = 'apps.stock'

    def ready(self):
        from apps.stock import signals  # noqa: F401
