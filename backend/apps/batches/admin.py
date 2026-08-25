from django.contrib import admin

from apps.batches.models import BatchClosingReport, DailyLog, PoultryBatch

admin.site.register(PoultryBatch)
admin.site.register(DailyLog)
admin.site.register(BatchClosingReport)
