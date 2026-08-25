from django.contrib import admin

from apps.maintenance.models import EquipmentFault, UnusualCase

admin.site.register(EquipmentFault)
admin.site.register(UnusualCase)
