"""Split by resource (2026-08-26 reorg, following the same pattern already used for
`apps.batches.views` — see that package's own `__init__.py`): houses.py (house CRUD),
protocol.py (protocol lines + categories), tasks.py ("tâches à effectuer maintenant" +
assignment + "Mes tâches"), milestones.py (cycle timeline + "Prochaines 48h"). Re-exported here
so `apps/houses/urls.py` keeps importing `from apps.houses import views` and referencing
`views.XxxView` without change.
"""
from apps.houses.views.houses import HouseDetailView, HouseListCreateView
from apps.houses.views.milestones import HouseMilestonesView, Upcoming48hView
from apps.houses.views.protocol import HouseProtocolView, ProtocolCategoryDetailView, ProtocolCategoryListCreateView
from apps.houses.views.tasks import (
    AssignableUsersView, HouseAssignmentsView, HouseTaskAssignView, HouseTaskCompleteView,
    HouseTaskUncompleteView, HouseTasksNowView, MyTasksView,
)

__all__ = [
    'HouseListCreateView', 'HouseDetailView',
    'HouseProtocolView', 'ProtocolCategoryListCreateView', 'ProtocolCategoryDetailView',
    'HouseTasksNowView', 'HouseTaskAssignView', 'HouseTaskCompleteView', 'HouseTaskUncompleteView',
    'MyTasksView', 'AssignableUsersView', 'HouseAssignmentsView',
    'HouseMilestonesView', 'Upcoming48hView',
]
