from django.contrib import admin

from apps.finance.models import Expense, PurchaseOrder, Sale

admin.site.register(Expense)
admin.site.register(Sale)
admin.site.register(PurchaseOrder)
