"""Web Push delivery (2026-08-31) — desktop notifications that fire even with no Winchicken
tab open.

`send_web_push_to_farm` is the only place `pywebpush` is called. It is invoked from
`apps.alerts.tasks.send_web_push_task` (queued, never inline in a request) which itself is
scheduled by `apps.alerts.notify.notify_farm` on transaction commit. A subscription the push
service reports as gone (HTTP 404/410) is deleted so it is not retried.
"""
from __future__ import annotations

import json
import logging

from django.conf import settings
from pywebpush import WebPushException, webpush

logger = logging.getLogger(__name__)


def _vapid_claims() -> dict:
    return {'sub': settings.VAPID_SUBJECT}


def send_web_push_to_farm(farm_id: int, payload: dict) -> int:
    """Push `payload` (dict — serialised to JSON for the service worker) to every browser
    subscribed for the farm. Returns the number of successful deliveries. No-op when push is
    disabled (no VAPID keys) or the farm has no subscriptions."""
    if not settings.WEB_PUSH_ENABLED:
        return 0

    from apps.alerts.models import PushSubscription

    subs = list(PushSubscription.objects.filter(farm_id=farm_id))
    if not subs:
        return 0

    data = json.dumps(payload)
    sent, dead = 0, []
    for sub in subs:
        try:
            webpush(
                subscription_info={
                    'endpoint': sub.endpoint,
                    'keys': {'p256dh': sub.p256dh, 'auth': sub.auth},
                },
                data=data,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims=dict(_vapid_claims()),
                ttl=86400,
            )
            sent += 1
        except WebPushException as exc:
            status = getattr(exc.response, 'status_code', None)
            if status in (404, 410):
                dead.append(sub.id)
            else:
                logger.warning('web push failed (sub %s, status %s): %s', sub.id, status, exc)
        except Exception:  # noqa: BLE001 - never let a bad subscription break the batch
            logger.exception('web push crashed for subscription %s', sub.id)

    if dead:
        PushSubscription.objects.filter(id__in=dead).delete()
        logger.info('pruned %d dead push subscriptions', len(dead))
    return sent
