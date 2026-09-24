from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'apps.core'

    def ready(self):
        # Every model FloatField becomes a FiniteFloatField in every ModelSerializer: one place,
        # rather than a declaration per field per app that the next field would forget.
        from django.db import models
        from rest_framework import serializers

        from apps.core.fields import FiniteFloatField

        serializers.ModelSerializer.serializer_field_mapping[models.FloatField] = FiniteFloatField
