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

        # Any write invalidates the cached aggregate screens (apps.core.cache).
        from django.db.models.signals import m2m_changed, post_delete, post_save

        from apps.core.cache import on_model_change

        for name, signal in (('save', post_save), ('delete', post_delete), ('m2m', m2m_changed)):
            signal.connect(on_model_change, dispatch_uid=f'winchicken-cache-{name}')
