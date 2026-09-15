from django.urls import path

from apps.houses import views

urlpatterns = [
    path('houses/', views.HouseListCreateView.as_view(), name='house-list'),
    path('houses/<str:house_code>/', views.HouseDetailView.as_view(), name='house-detail'),
    path('houses/<str:house_code>/protocol/', views.HouseProtocolView.as_view(), name='house-protocol'),
    path('houses/<str:house_code>/protocol-categories/', views.ProtocolCategoryListCreateView.as_view(), name='house-protocol-categories'),
    path('houses/<str:house_code>/protocol-categories/<int:pk>/', views.ProtocolCategoryDetailView.as_view(), name='house-protocol-category-detail'),
    path('houses/<str:house_code>/tasks-now/', views.HouseTasksNowView.as_view(), name='house-tasks-now'),
    path('houses/<str:house_code>/tasks-now/<str:task_id>/assign/', views.HouseTaskAssignView.as_view(), name='house-task-assign'),
    path('houses/<str:house_code>/tasks-now/<str:task_id>/complete/', views.HouseTaskCompleteView.as_view(), name='house-task-complete'),
    path('houses/<str:house_code>/tasks-now/<str:task_id>/uncomplete/', views.HouseTaskUncompleteView.as_view(), name='house-task-uncomplete'),
    path('houses/<str:house_code>/assignments/', views.HouseAssignmentsView.as_view(), name='house-assignments'),
    path('tasks/mine/', views.MyTasksView.as_view(), name='tasks-mine'),
    path('tasks/assignable-users/', views.AssignableUsersView.as_view(), name='tasks-assignable-users'),
    path('houses/<str:house_code>/milestones/', views.HouseMilestonesView.as_view(), name='house-milestones'),
    path('tasks/upcoming/', views.Upcoming48hView.as_view(), name='tasks-upcoming'),
]
