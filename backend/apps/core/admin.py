from django.contrib import admin

from apps.core.models import Admin, Cashier, Farm, FarmManager, Farmer, SecondaryAdmin, Technician, User, Worker

admin.site.register(Farm)
admin.site.register(User)
admin.site.register(Admin)
admin.site.register(SecondaryAdmin)
admin.site.register(FarmManager)
admin.site.register(Farmer)
admin.site.register(Worker)
admin.site.register(Technician)
admin.site.register(Cashier)
