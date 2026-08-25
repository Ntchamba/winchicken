from django.urls import path

from apps.protocols import views

urlpatterns = [
    path('protocols/onboarding/', views.OnboardingView.as_view(), name='protocols-onboarding'),
]
