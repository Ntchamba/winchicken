"""
Django settings for the Winchicken backend.
"""

from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-winchicken-dev-key-change-in-production')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'drf_spectacular',
    'corsheaders',
    'apps.core',
    'apps.houses',
    'apps.batches',
    'apps.stock',
    'apps.maintenance',
    'apps.finance',
    'apps.alerts',
    'apps.protocols',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='winchicken'),
        'USER': config('DB_USER', default='winchicken'),
        'PASSWORD': config('DB_PASSWORD', default='winchicken'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

AUTH_USER_MODEL = 'core.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'fr'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Wall-clock timezone the farm physically operates in. `TIME_ZONE` above stays 'UTC' (all
# timestamps are stored/served in UTC); this is used ONLY to interpret user-entered wall-clock
# values — currently `AlertRule.trigger_time` — against "now" when firing scheduled task
# reminders (apps.alerts.services.fire_scheduled_alerts). Default Africa/Douala (WAT, UTC+1):
# this deployment's default currency is XAF (Central/West Africa). Override per deployment with
# the FARM_TIME_ZONE env var if the farm is elsewhere — a wrong value here silently sends
# reminders an hour or more off.
FARM_TIME_ZONE = config('FARM_TIME_ZONE', default='Africa/Douala')

STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# OpenAPI schema (drf-spectacular) — served at /api/schema/ (raw) and /api/docs/
# (Swagger UI), both behind the same JWT auth as the rest of the API (see
# config/urls.py: neither view is added to the public/AllowAny endpoint list).
SPECTACULAR_SETTINGS = {
    'TITLE': 'Winchicken API',
    'DESCRIPTION': (
        'Single-farm poultry management backend — houses, batches, stock, '
        'maintenance, finance and SMS alerts. All endpoints require a JWT '
        'access token (Authorization: Bearer <token>) except '
        '/api/health/, /api/farm/exists/, /api/farm/create/, '
        '/api/auth/login/, /api/auth/refresh/, /api/contact/ and /api/newsletter/.'
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    # drf-spectacular's SpectacularAPIView/SpectacularSwaggerView default their own
    # permission_classes to AllowAny regardless of REST_FRAMEWORK's
    # DEFAULT_PERMISSION_CLASSES — without this override /api/schema/ and /api/docs/
    # would be reachable unauthenticated despite the comment above and despite not
    # being listed as public anywhere else.
    'SERVE_PERMISSIONS': ['rest_framework.permissions.IsAuthenticated'],
    # ProtocolTemplate.from_unit and .to_unit share the same DAY/WEEK/MONTH choice set
    # (apps.protocols.models.ProtocolUnit) — without this override drf-spectacular emits two
    # differently-named enum components (FromUnitEnum / ToUnitEnum) for what is really one enum.
    'ENUM_NAME_OVERRIDES': {
        'ProtocolUnitEnum': 'apps.protocols.models.ProtocolUnit',
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=30),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
}

CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='http://localhost:5173', cast=Csv())

# Celery — async, idempotent SMS sending (see apps.alerts)
CELERY_BROKER_URL = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TASK_TRACK_STARTED = True

# SMS provider — never hardcoded, always from env
SMS_PROVIDER = config('SMS_PROVIDER', default='console')
SMS_PROVIDER_API_KEY = config('SMS_PROVIDER_API_KEY', default='')
SMS_PROVIDER_SENDER_ID = config('SMS_PROVIDER_SENDER_ID', default='WINCHICKEN')
