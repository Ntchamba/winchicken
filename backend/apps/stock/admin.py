from django.contrib import admin

from apps.stock.models import StockItem, StockMovement, Vaccination

admin.site.register(StockItem)
admin.site.register(StockMovement)
admin.site.register(Vaccination)
