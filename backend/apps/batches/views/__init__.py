"""Split by resource (2026-08-25 reorg — see docs/architecture.md): batches.py (batch CRUD +
close), daily_logs.py (DailyLog create + quick-entry upsert), kpi.py (growth curves + weekly
KPI). Re-exported here so `apps/batches/urls.py` keeps importing `from apps.batches import
views` and referencing `views.XxxView` without change.
"""
from apps.batches.views.batches import BatchCloseView, PoultryBatchDetailView, PoultryBatchListCreateView
from apps.batches.views.daily_logs import DailyLogListCreateView, DailyLogQuickEntryView
from apps.batches.views.kpi import FarmHealthScoreView, GrowthCurvesView, WeeklyKpiView

__all__ = [
    'PoultryBatchListCreateView', 'PoultryBatchDetailView', 'BatchCloseView',
    'DailyLogListCreateView', 'DailyLogQuickEntryView',
    'GrowthCurvesView', 'WeeklyKpiView', 'FarmHealthScoreView',
]
