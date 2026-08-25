from django.urls import path

from apps.batches import views

urlpatterns = [
    path('batches/', views.PoultryBatchListCreateView.as_view(), name='batch-list'),
    path('batches/<str:batch_code>/close/', views.BatchCloseView.as_view(), name='batch-close'),
    path('batches/<str:batch_code>/daily-logs/', views.DailyLogListCreateView.as_view(), name='batch-daily-logs'),
    path('batches/<str:batch_code>/kpi/weekly/', views.WeeklyKpiView.as_view(), name='batch-kpi-weekly'),
]
