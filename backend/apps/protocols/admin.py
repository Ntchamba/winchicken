from django.contrib import admin

from apps.protocols.models import ProtocolTemplate, ProtocolTimeSlot

admin.site.register(ProtocolTemplate)
admin.site.register(ProtocolTimeSlot)
