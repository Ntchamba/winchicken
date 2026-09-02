from django.urls import path

from apps.protocols import views

urlpatterns = [
    path('protocols/onboarding/', views.OnboardingView.as_view(), name='protocols-onboarding'),
    path('protocols/schedule/', views.ScheduleView.as_view(), name='protocols-schedule'),
    path('protocols/import-xlsx/', views.ProtocolImportView.as_view(), name='protocols-import-xlsx'),
    path(
        'protocols/import-template.xlsx',
        views.ProtocolImportTemplateView.as_view(),
        name='protocols-import-template',
    ),
]
