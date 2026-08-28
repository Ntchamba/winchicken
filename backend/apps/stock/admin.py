from django.contrib import admin

from apps.stock.models import StockCategory, StockItem, StockMovement, Supplier, Vaccination

admin.site.register(StockCategory)
admin.site.register(StockItem)
admin.site.register(StockMovement)
admin.site.register(Supplier)
admin.site.register(Vaccination)
