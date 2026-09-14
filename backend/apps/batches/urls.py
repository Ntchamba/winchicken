from django.urls import path

from apps.batches import views

urlpatterns = [
    path('batches/', views.PoultryBatchListCreateView.as_view(), name='batch-list'),
    path('batches/growth-curves/', views.GrowthCurvesView.as_view(), name='batch-growth-curves'),
    path('batches/health-score/', views.FarmHealthScoreView.as_view(), name='batch-health-score'),
    path('batches/<str:batch_code>/', views.PoultryBatchDetailView.as_view(), name='batch-detail'),
    path('batches/<str:batch_code>/close/', views.BatchCloseView.as_view(), name='batch-close'),
    path('batches/<str:batch_code>/daily-logs/', views.DailyLogListCreateView.as_view(), name='batch-daily-logs'),
    path('batches/<str:batch_code>/daily-logs/quick-entry/', views.DailyLogQuickEntryView.as_view(), name='batch-daily-log-quick-entry'),
    path('batches/<str:batch_code>/kpi/weekly/', views.WeeklyKpiView.as_view(), name='batch-kpi-weekly'),
]
