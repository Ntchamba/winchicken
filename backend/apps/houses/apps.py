from django.apps import AppConfig


class HousesConfig(AppConfig):
    name = 'apps.houses'

    def ready(self):
        from apps.houses import signals  # noqa: F401
