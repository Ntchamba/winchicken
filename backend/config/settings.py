"""
Django settings for the Winchicken backend.
"""

import sys
from datetime import timedelta
from pathlib import Path

from decouple import Csv, config
from django.core.management.utils import get_random_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent

# No hardcoded fallback: a committed default is a key every deployment would share, so anyone
# could forge this app's JWTs (HS256 is signed with it). Unset -> a fresh random key each boot
# (get_random_secret_key never raises, so this is safe at import time; sessions/tokens simply do
# not survive a restart until SECRET_KEY is set in the environment, which every stack and the
# installer do). Security review 2026-09-26 (MEDIUM-4).
SECRET_KEY = config('SECRET_KEY', default='') or get_random_secret_key()
# Fail safe, not open: an operator who forgets to set DEBUG gets production behaviour (no
# tracebacks, no settings dump), not a debug page leaking DB and Twilio secrets to any logged-in
# user. Dev and test compose set DEBUG=True explicitly. Security review 2026-09-26 (HIGH-1).
DEBUG = config('DEBUG', default=False, cast=bool)
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
    'apps.search',
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
    'apps.core.cache.InvalidateOnWriteMiddleware',
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

# Wall-clock timezone the farm physically operates in — and, since 2026-09-12, the timezone the
# whole app runs on. Default Africa/Douala (WAT, UTC+1): this deployment's default currency is
# XAF (Central/West Africa). Override per deployment with the FARM_TIME_ZONE env var if the farm
# is elsewhere — a wrong value here silently mis-dates every entry and sends reminders an hour
# or more off.
#
# `TIME_ZONE` follows it instead of being set independently, so the app has exactly one timezone
# concept. It was hardcoded 'UTC' until 2026-09-12, which mis-dated everything recorded between
# local midnight and 01:00 (UTC was still on the previous day) and held a fresh batch at
# "Jour 0" for that hour. `USE_TZ` stays True: instants are still stored in UTC, they are just
# rendered — and bucketed into days — in farm-local time.
FARM_TIME_ZONE = config('FARM_TIME_ZONE', default='Africa/Douala')
TIME_ZONE = FARM_TIME_ZONE
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
# collectstatic target for the production stack (docker-compose.prod.yml): a named volume nginx
# serves at /static/ (Django admin, API docs). Unused in development, where runserver serves them.
STATIC_ROOT = config('STATIC_ROOT', default=str(BASE_DIR / 'staticfiles'))
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'apps.core.pagination.StablePageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    # Rate limiting (security review 2026-09-26, HIGH-2). ScopedRateThrottle only throttles the
    # views that set `throttle_scope`, so every other endpoint is unaffected; the sensitive ones
    # (login, the farm-reset password oracle, the Excel imports) opt in below. Counts live in the
    # `default` cache — Redis in the stacks, so the limit holds across gunicorn workers; keyed by
    # user when authenticated, by client IP otherwise. Rates are deliberately generous enough for
    # a real farmer retyping a password, tight enough to stop automated brute force.
    'DEFAULT_THROTTLE_CLASSES': ('rest_framework.throttling.ScopedRateThrottle',),
    'DEFAULT_THROTTLE_RATES': {
        'login': '10/min',
        'farm_reset': '5/min',
        'import': '12/min',
    },
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

# Factory reset audit trail (2026-08-26) — plain-text, on the filesystem, deliberately *not* a DB
# table: POST /api/farm/reset/ wipes every farm-scoped row in one transaction, so a DB-backed log
# would be wiped right along with everything else it was supposed to be evidence of. `logs/` is a
# named volume in docker-compose.yml (`winchicken_backend_logs`), not part of the bind-mounted
# source tree — Docker owns it, so the container's non-root `appuser` can always write to it
# whatever uid owns ./backend on the host.
LOGS_DIR = BASE_DIR / 'logs'
FACTORY_RESET_LOG = LOGS_DIR / 'factory_reset.log'


def _factory_reset_log_path() -> Path | None:
    """The audit-log path if it is genuinely writable, otherwise None.

    This module is imported before Django is configured, so anything raising here is an
    unrecoverable crash-loop: no server, no error page, just a restarting container. That is
    exactly what used to happen under rootless Docker, where host uid 1000 maps to uid 0 and the
    bind-mounted `/app` therefore arrives root-owned, so `appuser` cannot create `logs/` (see
    docs/deviations.md). An unwritable audit trail is worth shouting about; it is not worth
    taking the whole API down for, so we degrade to stderr instead.

    `mkdir` succeeding is not sufficient evidence — the directory can already exist and still be
    unwritable, which is the rootless case — so the probe is a real append-mode open.
    """
    try:
        LOGS_DIR.mkdir(exist_ok=True)
        with open(FACTORY_RESET_LOG, 'a', encoding='utf-8'):
            pass
    except OSError as exc:
        print(
            f'WARNING: factory-reset audit log unavailable at {FACTORY_RESET_LOG} ({exc}). '
            'Falling back to stderr — the trail will only survive in the container logs. '
            'Fix the mount/ownership before relying on it as evidence.',
            file=sys.stderr,
            flush=True,
        )
        return None
    return FACTORY_RESET_LOG


_FACTORY_RESET_LOG_PATH = _factory_reset_log_path()

# Same logger name either way, so apps.core.services never has to know which one it got.
_FACTORY_RESET_HANDLER = (
    {
        'class': 'logging.FileHandler',
        'filename': _FACTORY_RESET_LOG_PATH,
        'formatter': 'plain',
    }
    if _FACTORY_RESET_LOG_PATH is not None
    else {
        'class': 'logging.StreamHandler',
        'stream': 'ext://sys.stderr',
        'formatter': 'plain',
    }
)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'plain': {'format': '%(asctime)s %(message)s'},
    },
    'handlers': {
        'factory_reset_file': _FACTORY_RESET_HANDLER,
    },
    'loggers': {
        'factory_reset': {
            'handlers': ['factory_reset_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Celery — async, idempotent SMS sending (see apps.alerts)
CELERY_BROKER_URL = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TASK_TRACK_STARTED = True
# Beat resolves crontab schedules in this timezone. The only current entry is `crontab()` (every
# minute), which is timezone-insensitive — this is here so the first hour-specific schedule
# someone adds is not silently an hour off. Instants stay UTC on the wire (`enable_utc` default).
CELERY_TIMEZONE = FARM_TIME_ZONE

# Cache — the stack's Redis (already there for Celery), shared by web and worker: background
# import jobs keep their progress here, and the overview/dashboard aggregates are cached for a
# few seconds. `memory://` (load_test.sh, no broker) and the test runner get an in-process
# cache instead, so a test never reads or writes the live stack's keys. String checks only:
# nothing here may raise at import time.
_REDIS_URL = config('REDIS_URL', default='redis://localhost:6379/0')
# `responses` holds the cached aggregate responses (apps.core.cache) apart from `default`, so the
# test runner can switch that one off: tests write through the ORM inside transactions that never
# commit, and the invalidation runs on commit.
if _REDIS_URL.startswith(('redis://', 'rediss://')):
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': _REDIS_URL,
            'KEY_PREFIX': 'winchicken',
            'TIMEOUT': 300,
        },
        'responses': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': _REDIS_URL,
            'KEY_PREFIX': 'winchicken-resp',
            'TIMEOUT': 30,
        },
    }
else:
    CACHES = {
        'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
        'responses': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'responses', 'TIMEOUT': 30},
    }

# SMS provider — never hardcoded, always from env
SMS_PROVIDER = config('SMS_PROVIDER', default='console')
SMS_PROVIDER_API_KEY = config('SMS_PROVIDER_API_KEY', default='')
SMS_PROVIDER_SENDER_ID = config('SMS_PROVIDER_SENDER_ID', default='WINCHICKEN')

# Twilio — only read when SMS_PROVIDER=twilio (apps.alerts.providers.twilio.TwilioSmsProvider).
TWILIO_ACCOUNT_SID = config('TWILIO_ACCOUNT_SID', default='')
TWILIO_AUTH_TOKEN = config('TWILIO_AUTH_TOKEN', default='')
TWILIO_PHONE_NUMBER = config('TWILIO_PHONE_NUMBER', default='')
# Trial-account shim: a Twilio *trial* account rejects any custom message body ("Trial
# accounts can only use predefined SMS templates"). When this is set to a predefined template
# name (e.g. "sms_appointment_reminders"), TwilioSmsProvider sends that template instead of the
# real body — so the scheduling/delivery path can be demoed end to end on a trial account. The
# real body it *would* have sent is logged. Leave empty on a paid account.
TWILIO_TRIAL_TEMPLATE = config('TWILIO_TRIAL_TEMPLATE', default='')

# --- Web Push (desktop notifications, works with the browser closed) ------------
# VAPID keypair (base64url, uncompressed P-256). Generate once with:
#   docker compose exec web python manage.py generate_vapid_keys
# then paste both values into backend/.env. Push is disabled while either is blank.
VAPID_PUBLIC_KEY = config('VAPID_PUBLIC_KEY', default='')
VAPID_PRIVATE_KEY = config('VAPID_PRIVATE_KEY', default='')
# "mailto:" (or https) contact the push service can reach — required by the spec.
VAPID_SUBJECT = config('VAPID_SUBJECT', default='mailto:admin@winchicken.local')
WEB_PUSH_ENABLED = config('WEB_PUSH_ENABLED', default=True, cast=bool) and bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY)

# --- Test isolation ------------------------------------------------------------------------
# The stacks' .env holds live Twilio and VAPID credentials, and the test runner shares the
# stack's Redis with a running worker. Under `manage.py test` or pytest: SMS goes to the console
# provider, no Web Push is sent, and Celery tasks run in-process instead of being queued — a
# queued SMS id from the test database would otherwise be looked up by the live worker in the
# stack's own database and sent for real. Plain comparisons only: nothing here may raise.
RUNNING_TESTS = (len(sys.argv) > 1 and sys.argv[1] == 'test') or 'pytest' in sys.modules
if RUNNING_TESTS:
    SMS_PROVIDER = 'console'
    WEB_PUSH_ENABLED = False
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_BROKER_URL = 'memory://'
    # No throttling under the test runner: the suite logs in and imports far faster than a
    # human, and a shared LocMemCache would carry counts between tests and fail them at random.
    REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] = ()
    CACHES = {
        'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
        'responses': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'},
    }
