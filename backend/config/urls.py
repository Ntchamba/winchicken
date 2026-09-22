from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('apps.core.urls')),
    path('api/', include('apps.houses.urls')),
    path('api/', include('apps.protocols.urls')),
    path('api/', include('apps.batches.urls')),
    path('api/', include('apps.stock.urls')),
    path('api/', include('apps.maintenance.urls')),
    path('api/', include('apps.finance.urls')),
    path('api/', include('apps.alerts.urls')),
    path('api/', include('apps.search.urls')),
    # OpenAPI schema + Swagger UI. Deliberately NOT added to any AllowAny/public
    # endpoint list: both views inherit the project-wide default permission
    # (IsAuthenticated, REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES']) since
    # neither SpectacularAPIView nor SpectacularSwaggerView is given its own
    # permission_classes here — a valid JWT access token is required for both.
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]
