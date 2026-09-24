"""Serializer fields shared by every app."""
import math

from rest_framework import serializers


class FiniteFloatField(serializers.FloatField):
    """A FloatField that refuses NaN and infinity.

    DRF's FloatField takes whatever float() takes, which includes "nan", "inf" and "1e400"; Postgres
    then stores them, and one such row turns every total that sums it into NaN (a NaN sale quantity
    made every finance figure NaN and the JSON unreadable). Registered for every model FloatField
    in CoreConfig.ready(), so ModelSerializers get it without declaring anything.
    """

    default_error_messages = {'not_finite': 'Saisissez un nombre valide.'}

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if not math.isfinite(value):
            self.fail('not_finite')
        return value
