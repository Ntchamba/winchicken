"""`notify_farm` — the single entry point every "something changed" signal calls to raise a
desktop notification (2026-08-31).

It queues `send_web_push_task` on the current transaction's commit, so a rolled-back write
never notifies and the HTTP request is never blocked on the push service. Safe to call with no
open transaction (runs on the next commit / immediately in AUTOCOMMIT).
"""
from __future__ import annotations

from django.conf import settings
from django.db import transaction


def notify_farm(farm_id: int, *, title: str, body: str, url: str = '/', tag: str | None = None) -> None:
    if not settings.WEB_PUSH_ENABLED or not farm_id:
        return
    from apps.alerts.tasks import send_web_push_task

    payload = {'title': title, 'body': body, 'url': url, 'tag': tag or ''}
    transaction.on_commit(lambda: send_web_push_task.delay(farm_id, payload))
