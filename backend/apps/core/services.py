from decimal import Decimal, InvalidOperation
import logging

from django.db import transaction

reset_logger = logging.getLogger('factory_reset')


def record_audit_log(user, action, target_description):
    """The single call site for writing an `AuditLogEntry` (2026-08-26, docs/deviations.md
    Part 15) — every view that performs a consequential action calls this instead of
    constructing the model directly, so the write shape (farm from `user.farm`,
    `user_name_snapshot` captured now) stays in one place rather than copy-pasted per view.

    `action` is a short dotted code (`"batch.created"`, `"protocol.updated"`, ...) — see
    `frontend/src/pages/dashboard/AuditLogPage.jsx`'s `ACTION_LABELS` for the French label each
    one maps to; keep the two in sync when adding a new action.
    """
    from apps.core.models import AuditLogEntry
    AuditLogEntry.objects.create(
        farm=user.farm, user=user, user_name_snapshot=user.name,
        action=action, target_description=target_description,
    )


def factory_reset_farm(farm, actor):
    """Irreversibly wipes the single `Farm` row and everything that cascades from it — every
    `PoultryHouse`/`PoultryBatch`/`DailyLog`/`BatchClosingReport`, every `StockItem`/
    `StockMovement`/`Vaccination`, `EquipmentFault`/`UnusualCase`, `Expense`/`Sale`/
    `PurchaseOrder`, `AlertRule`/`Alert`/`SmsMessage`/`NotificationPreference`,
    `ProtocolCategory`/`ProtocolTemplate`, and every `User` (+ role-subtype row) including
    `actor` themselves — back to a genuinely fresh install (`GET /api/farm/exists/` → False).

    Every one of those tables FKs to `Farm` (directly or transitively) with `on_delete=CASCADE`
    (verified against every app's models.py, 2026-08-26) — a single `farm.delete()` is enough;
    no per-app cleanup pass is needed. The two tables that are *not* wiped, `ContactMessage` and
    `NewsletterSubscriber`, are deliberately excluded: they're public landing-page submissions,
    not farm data, and aren't in `farm_management_schema_en.puml`.

    Logged to the `factory_reset` logger (settings.LOGGING → `backend/logs/factory_reset.log`,
    plain text, on the filesystem) *before* the delete — once this returns there is no DB row
    left anywhere to reconstruct who did this or when, so that file is the only remaining trace.
    `actor`'s own account is gone by the time this returns too: nothing in `apps.core.views` or
    the frontend needs it again after the call (the caller already has the name/email it needs
    for the response, captured before this runs).

    No explicit token-blacklist step: `apps.core` doesn't have `rest_framework_simplejwt.
    token_blacklist` installed, and doesn't need it here — every issued access token's next use
    calls `JWTAuthentication.get_user()`, which does a real `User.objects.get(...)` lookup and
    raises `AuthenticationFailed` (401) the moment that row is gone. A refresh token can still be
    exchanged for a *new* access token after this (SimpleJWT's refresh view never touches the
    `User` table), but that new token 401s on its very first real use for the same reason — so
    every session ends up rejected either way, just not on a token-blacklist table this action
    would otherwise have to remember to also wipe.
    """
    reset_logger.info('FACTORY RESET farm=%r admin_email=%s admin_name=%r', farm.name, actor.email, actor.name)
    with transaction.atomic():
        # Written for consistency with every other consequential action going through this one
        # function (docs/deviations.md Part 15) — it does not actually survive: `AuditLogEntry`
        # is farm-scoped and CASCADEs with everything else the line below deletes. The external
        # log line just above is the record that's actually still readable afterward.
        record_audit_log(actor, 'farm.reset', farm.name)
        farm.delete()


def is_farm_configured(farm):
    """True once the farm has >=1 PoultryHouse with >=1 ProtocolTemplate line AND >=1 StockItem.

    The employees onboarding step is deliberately excluded from this condition (cahier des
    charges 5.3) — it is skippable without blocking dashboard access.
    """
    from apps.houses.models import PoultryHouse
    from apps.stock.models import StockItem

    has_configured_house = PoultryHouse.objects.filter(
        farm=farm, protocol_lines__isnull=False
    ).distinct().exists()
    has_stock_item = StockItem.objects.filter(farm=farm).exists()
    return has_configured_house and has_stock_item


# `User.hourly_rate` is DecimalField(max_digits=10, decimal_places=2): anything at or over 10^8
# cannot be stored. Kept here, next to its one parser, so the rate screen and the employee
# Excel import apply the same rule.
HOURLY_RATE_LIMIT = Decimal('100000000')


class InvalidHourlyRate(ValueError):
    """The French message is the exception's text."""


def parse_hourly_rate(raw):
    """`None` for an empty value, else a finite `Decimal` in [0, 10^8). Accepts a decimal comma.
    The employee import used to skip this: it stored a -300 FCFA rate (a negative salary) and
    reported an oversized one with PostgreSQL's English "numeric field overflow" text
    (campaign 9, finding B10/B11)."""
    if raw in (None, ''):
        return None
    try:
        rate = Decimal(str(raw).strip().replace(',', '.'))
    except InvalidOperation:
        raise InvalidHourlyRate('Doit être un nombre valide.')
    # Decimal() also takes "NaN", "Infinity" and negatives; a salary is hours x rate.
    if not rate.is_finite() or rate < 0 or rate >= HOURLY_RATE_LIMIT:
        raise InvalidHourlyRate('Doit être un montant positif valide.')
    return rate
