"""Short-lived cache for the farm-wide aggregate screens (2026-09-25).

The "Bilan global" tree and the dashboard's health score and growth curves recompute the same
aggregates for every visit from every phone. They are cached in the `responses` cache for
`RESPONSE_TTL` seconds under a key that carries a farm-wide data version, and every write bumps
that version, so a change made in the app shows on the very next load — this codebase has been
bitten by stale screens before (sidebar staleness), and a cache must not bring that back.

What bumps the version, after the transaction commits (a reader between the write and the
commit would otherwise cache the old data under the new version):
- any model save / delete / many-to-many change, wherever it comes from (API, Celery, admin);
- any successful POST / PUT / PATCH / DELETE request — this catches `QuerySet.update()` and
  `bulk_create`, which send no signals.
The TTL bounds what neither sees (a raw SQL write). The key also carries today's farm-local
date, so nothing computed yesterday survives midnight. A cache that cannot be reached is
skipped: the screen is computed as if there were no cache, never an error.
"""
import functools
import logging

from django.core.cache import caches
from django.db import transaction
from django.utils import timezone
from rest_framework.response import Response

logger = logging.getLogger(__name__)

RESPONSE_TTL = 30
VERSION_KEY = 'farm-data-version'
_SAFE_METHODS = {'GET', 'HEAD', 'OPTIONS'}
# Writes that change nothing any cached screen shows.
_IGNORED_APPS = {'sessions', 'admin', 'contenttypes', 'token_blacklist'}


def _cache():
    return caches['responses']


def data_version():
    try:
        return _cache().get_or_set(VERSION_KEY, 0, None)
    except Exception:
        logger.warning('Response cache unreachable', exc_info=True)
        return None


def bump_data_version():
    cache = _cache()
    try:
        try:
            cache.incr(VERSION_KEY)
        except ValueError:  # not set yet (or evicted)
            cache.set(VERSION_KEY, 1, None)
    except Exception:
        logger.warning('Response cache unreachable', exc_info=True)


def _bump_on_commit():
    bump_data_version()


def bump_after_commit(using=None):
    """One bump per transaction, however many rows it writes. Deduplicated against Django's own
    on-commit queue rather than a flag of ours: a rollback empties that queue, where a flag would
    stay set and swallow every later bump on the connection."""
    conn = transaction.get_connection(using)
    if not conn.in_atomic_block:
        bump_data_version()
        return
    if any(entry[1] is _bump_on_commit for entry in conn.run_on_commit):
        return
    transaction.on_commit(_bump_on_commit, using=using)


def on_model_change(sender, using=None, **kwargs):
    if sender._meta.app_label in _IGNORED_APPS:
        return
    bump_after_commit(using)


def cached_farm_response(view_get):
    """Decorates an APIView `get` whose response depends only on the farm and the query string
    — never on who asks (permissions still run first, in `dispatch`)."""

    @functools.wraps(view_get)
    def wrapper(self, request, *args, **kwargs):
        version = data_version()
        if version is None or not request.user.farm_id:
            return view_get(self, request, *args, **kwargs)
        key = f'{version}:{timezone.localdate().isoformat()}:{request.user.farm_id}:{request.get_full_path()}'
        try:
            hit = _cache().get(key)
        except Exception:
            hit = None
        if hit is not None:
            return Response(hit)
        response = view_get(self, request, *args, **kwargs)
        if response.status_code == 200:
            try:
                _cache().set(key, response.data, RESPONSE_TTL)
            except Exception:
                logger.warning('Response cache unreachable', exc_info=True)
        return response

    return wrapper


class InvalidateOnWriteMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.method not in _SAFE_METHODS and response.status_code < 400:
            bump_data_version()
        return response
