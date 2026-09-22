from django.apps import AppConfig


class BatchesConfig(AppConfig):
    name = 'apps.batches'

    def ready(self):
        from apps.batches import signals  # noqa: F401
