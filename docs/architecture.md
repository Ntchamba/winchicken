# Architecture

This document describes the codebase as it actually exists (verified against
the source files listed inline), not as originally specified. See
`docs/deviations.md` for a consolidated list of every point where the
implementation diverges from `winchicken-cahier-des-charges.docx` /
`winchicken-spec-implementation-detaillee.docx`.

## Repository layout

```
backend/    Django project "config" — apps/ (core, houses, protocols, batches, stock,
            maintenance, finance, alerts), config/ (settings, urls, celery, asgi/wsgi)
frontend/   React + Vite app — components/, pages/, api/, context/, routes/, styles/, demo/
docker-compose.yml   db (Postgres 16) + redis + web (Django) + worker (Celery) + frontend (Vite)
docs/       This folder.
farm_management_schema_en.puml   Original data-model sketch — see docs/data-model.md for
            every place the real schema now differs from it.
winchicken-cahier-des-charges.docx              Functional scope spec.
winchicken-spec-implementation-detaillee.docx   Implementation-detail spec (endpoint shapes,
            formulas, chart specs, permission matrix).
```

## Security defaults

- **`SECRET_KEY`** has no insecure fallback — `backend/config/settings.py`
  raises `ImproperlyConfigured` at startup if it's unset or left at the
  `.env.example` placeholder. Every environment (including local dev) must
  set a real value in `backend/.env`.
- **`DEBUG`** defaults to `False`; local dev sets it explicitly in
  `backend/.env` (see `.env.example`).
- **Rate limiting** — DRF's `DEFAULT_THROTTLE_CLASSES` apply a per-user
  (`300/min`) and per-IP (`30/min`) rate limit across the API by default;
  the SMS delivery webhook (`POST /api/alerts/sms/webhook/`) uses its own
  `sms_webhook` scope (`120/min`) since it's called by the SMS provider, not
  a logged-in account.
- **Provider webhook signature verification** — `POST
  /api/alerts/sms/webhook/` (`apps.alerts.views.SmsDeliveryWebhookView`)
  verifies Twilio's `X-Twilio-Signature` header
  (`_verify_twilio_signature`, HMAC-SHA1 over the callback URL + sorted
  POST params, keyed with `SMS_PROVIDER_API_KEY`) before updating any
  `SmsMessage` row; a missing or invalid signature gets a `403` and no DB
  write.

## Backend: why each Django app exists

All apps live under `backend/apps/` and are registered in
`backend/config/settings.py` `INSTALLED_APPS`; every app's URLs are mounted
under `/api/` in `backend/config/urls.py`.

- **`apps.core`** — the root of everything else: `Farm` (the single-row
  installation root), `User` + the 7 role subtype models (class-table
  inheritance — see `docs/data-model.md`), authentication (JWT login,
  `/api/auth/me/`), employee CRUD, the onboarding gate (`services.py`,
  `serializers.py`), and two models with no functional dependency on the rest
  of the schema at all: `ContactMessage` and `NewsletterSubscriber` (public
  landing-page forms, not in the puml, not in the cahier des charges endpoint
  list — see `docs/deviations.md`).
- **`apps.houses`** — `PoultryHouse`, the physical building. Owns the
  `/api/houses/` CRUD and `/api/houses/{houseCode}/protocol/` (read/replace
  the house's protocol lines, which actually live in `apps.protocols`).
- **`apps.protocols`** — `ProtocolTemplate`, the reusable feeding / health /
  vaccination / cleaning schedule applied to every batch started in a house.
  Split into its own app (rather than nested under `apps.houses`) so that
  `apps.protocols.views.OnboardingView` can own the single onboarding
  transaction that creates a `PoultryHouse` + its `ProtocolTemplate` lines +
  (optionally) the first `PoultryBatch` together, without a circular
  dependency between the houses and batches apps.
- **`apps.batches`** — `PoultryBatch` (one flock, one house, one
  sanitary-void-enforced ACTIVE slot per house), `DailyLog` (daily
  mortality/feed/water/weight entry), `BatchClosingReport` (computed
  snapshot at closing), and `calculations.py` (mortality/FCR/weekly-KPI/BFR
  formulas — see `docs/calculations.md`).
- **`apps.stock`** — `StockItem` (warehouse item definitions),
  `StockMovement` (IN/OUT transactions — on-hand quantity is always derived
  from these, never stored), `Vaccination`. `calculations.py` holds
  `current_quantity`.
- **`apps.maintenance`** — `EquipmentFault`, `UnusualCase`. Declare-and-list
  plus a `PATCH` detail endpoint on each (`EquipmentFaultDetailView`,
  `UnusualCaseDetailView`) for status transitions / edits, role-restricted
  to match who is allowed to declare/report in the first place.
- **`apps.finance`** — `Expense`, `Sale`, `PurchaseOrder`, plus
  `calculations.py` (cash-on-hand, pending payables, ROI forecast, monthly
  summary, expense-category breakdown, and `batch_break_even` — break-even
  quantity + safety margin derived from a batch's own Expense/Sale rows,
  backing `GET /api/finance/break-even/?batch_code=`) and
  `apps.batches.calculations.bfr_estimate` (working-capital estimate,
  backing `GET /api/finance/working-capital/?batch_code=&as_of=`).
- **`apps.alerts`** — `AlertRule`, `Alert`, `SmsMessage`,
  `NotificationPreference`, plus the async SMS pipeline: `services.py`
  (`trigger_alert`, `check_low_stock`, `check_consumption_deviation`),
  `signals.py` (wires `StockMovement`/`DailyLog` `post_save` to those
  checks), `tasks.py` (`send_sms_task`, the Celery task with idempotency +
  exponential backoff, and `evaluate_scheduled_alert_rules`, the Celery
  Beat periodic task that drives every `SCHEDULED`-mode `AlertRule` — see
  "Scheduled alerts" below), `providers/` (pluggable SMS gateway interface:
  `console` for local dev, `twilio` for a real integration against
  Twilio's REST API). `GET /api/alerts/` is filterable by `?batch_code=`;
  `PATCH /api/alerts/{id}/` transitions an alert's status
  (`NEW` → `SENT`/`RESOLVED`). `POST /api/alerts/sms/webhook/` receives
  Twilio's delivery-status callback, signature-verified
  (`apps.alerts.views._verify_twilio_signature`) before touching the DB.

## Scheduled alerts (Celery Beat)

`config/celery.py` registers a `beat_schedule` entry
(`evaluate-scheduled-alert-rules`, every 5 minutes) that runs
`apps.alerts.tasks.evaluate_scheduled_alert_rules` — the only place
`SCHEDULED`-mode `AlertRule` rows are evaluated:

- **Recurring** rules (`frequency` DAILY/WEEKLY, `trigger_time` +
  `active_days` set) fire once per day when "now" falls within 5 minutes of
  `trigger_time` (and, for WEEKLY, today's weekday is in `active_days`);
  `fired_at` guards against firing twice on the same day.
- **`ONE_TIME`** rules (`fire_date` set, `batch` set) fire once, on that
  calendar date, then are marked `fired_at` permanently. These are how
  `VACCINE_DUE`/`SANITARY_VOID_END` alerts actually reach a user: at batch
  creation, `apps.batches.signals.expand_protocol_on_batch_created` (a
  `post_save` signal on `PoultryBatch`) calls
  `apps.protocols.services.expand_protocol_to_alert_rules`, which creates
  one `VACCINE_DUE` `AlertRule` per protocol line in a "Vaccination"
  category (fire date = `batch.start_date` + the line's offset) plus one
  `SANITARY_VOID_END` rule on `batch.planned_end_date`, if set — implementing
  the cahier des charges §4.6 rule ("ProtocolTemplate expands into AlertRule
  rows at batch creation, offset from PoultryBatch.startDate").

Requires the `beat` service in `docker-compose.yml`
(`celery -A config beat -l info`) running alongside `worker`.

## OpenAPI schema

`drf-spectacular` is wired into `backend/config/settings.py`
(`INSTALLED_APPS`, `REST_FRAMEWORK['DEFAULT_SCHEMA_CLASS']`,
`SPECTACULAR_SETTINGS`) and `backend/config/urls.py`:

- `GET /api/schema/` — raw OpenAPI 3.0 document (`SpectacularAPIView`).
- `GET /api/docs/` — Swagger UI (`SpectacularSwaggerView`).

Neither view sets its own `permission_classes` directly, but
drf-spectacular's `SpectacularAPIView`/`SpectacularSwaggerView` default
their own permissions to `AllowAny` internally regardless of
`REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES']` — fixed by setting
`SPECTACULAR_SETTINGS['SERVE_PERMISSIONS'] =
['rest_framework.permissions.IsAuthenticated']` explicitly (see
`docs/deviations.md`). Both endpoints require a JWT: `401` unauthenticated,
`200` with a valid access token.

```bash
cd backend && .venv/bin/python manage.py spectacular --file /tmp/winchicken-schema-check.yaml
```

regenerates the schema — run this (and update `docs/api-reference.md`) any
time an endpoint, serializer field, or permission class changes.

## Frontend routing map

Routing lives entirely in `frontend/src/App.jsx` (React Router v6,
`<Routes>`/`<Route>`), wrapped in `AuthProvider` (`context/AuthContext.jsx`):

| Path | Element | Guard |
|---|---|---|
| `/` | `LandingPage` | none (public) |
| `/create-farm` | `CreateFarmPage` | none (public) |
| `/login` | `LoginPage` | none (public) |
| `/demo` | `demo/DemoPage` | none (public, static demo data from `demo/demoData.js`) |
| `/onboarding/protocol` \| `/stock` \| `/employees` | `OnboardingLayout` + step pages | `ProtectedRoute allowUnconfigured` — requires login, but does *not* require `is_configured` |
| `/dashboard` (index) \| `/houses` \| `/houses/:houseCode` \| `/houses/:houseCode/protocol` \| `/finance` \| `/stock` \| `/employees` \| `/cashier` \| `/alerts` \| `/settings` | `DashboardShell` + page components | `ProtectedRoute` (no `allowUnconfigured`) — requires login **and** `is_configured` |
| `*` | redirect to `/` | — |

`ProtectedRoute` (`frontend/src/routes/ProtectedRoute.jsx`) is the single
guard component used for both onboarding and dashboard route groups; see
"Onboarding gate" below for its exact logic.

## Sidebar / layout composition

`DashboardShell` (`frontend/src/pages/dashboard/DashboardShell.jsx`) is the
`element` for the `/dashboard` route group's parent `<Route>`. On mount (and
whenever the route changes) it fetches `GET /api/houses/` and `GET /api/batches/`
together and maps the results into the shape `DashboardLayout` expects
(`{ houseCode, name, type }` — `type` is derived from each house's active batch's
`production_type`, defaulting to `"Broiler"` only when a house has no active batch;
see `docs/deviations.md` item 22 for the bug this replaced). It reads `user`/`logout` from
`AuthContext`, derives four role-gated booleans (`canManageHouses`,
`canSeeFinance`, `canSeeEmployees`, `canSeeCashier`) directly from
`user.role`, and renders:

```
DashboardShell
 └─ DashboardLayout (frontend/src/components/DashboardLayout.jsx)
     ├─ <aside class="sidebar"> — brand, "Vue d'ensemble", per-house links,
     │   "+ Nouveau bâtiment", Finance/Stock/Employés/Caissier links,
     │   Paramètres/Déconnexion, user avatar+name+role
     └─ <main class="dashboard-content">
         └─ <Outlet context={{ houses }} /> — the active dashboard page
```

Every one of `DashboardLayout`'s role-gated sidebar sections
(`canManageHouses`/`canSeeFinance`/`canSeeEmployees`/`canSeeCashier`) is
conditionally *not rendered* (not just disabled) when false — matching the
cahier des charges section 8 rule that a forbidden action must be hidden,
not merely greyed out.

## `is_configured` onboarding gate, end to end

1. **Backend source of truth** — `apps.core.services.is_farm_configured(farm)`:
   `True` iff the farm has at least one `PoultryHouse` with at least one
   `ProtocolTemplate` line **and** at least one `StockItem`. The employees
   step is deliberately excluded (cahier des charges 5.3 — skippable).
2. **Backend exposure** — two places compute it, both calling the same
   `is_farm_configured` function:
   - `apps.core.serializers.MeSerializer.get_is_configured` — used by
     `GET /api/auth/me/`.
   - `apps.core.serializers.WinchickenTokenObtainPairSerializer.validate` —
     included directly in the `POST /api/auth/login/` JWT response, so the
     frontend doesn't need a second round-trip right after login.
3. **Frontend consumption** — `AuthContext.refreshMe()` calls
   `GET /api/auth/me/` on load and after every login, storing the full
   response (including `is_configured`) as `user`.
4. **Frontend enforcement** — `routes/ProtectedRoute.jsx`:
   - No `user` (not logged in) → redirect to `/login`.
   - `user` exists, route is NOT `allowUnconfigured`, and
     `!user.is_configured` → redirect to `/onboarding/protocol`.
   - Otherwise renders the matched child route (`<Outlet />`).

   Onboarding routes themselves use `allowUnconfigured` so a user who hasn't
   finished onboarding isn't redirected away from the onboarding flow itself.

## Maintainability note

`docs/api-reference.md` and the OpenAPI schema (`GET /api/schema/`,
`GET /api/docs/`) describe the API surface as of this writing. **Both must
be regenerated whenever an endpoint, serializer field, or permission class
changes** — regenerate the schema with
`cd backend && .venv/bin/python manage.py spectacular --file /tmp/winchicken-schema-check.yaml`
(or point `--file` at a committed location) and update
`docs/api-reference.md`'s affected section by re-reading the corresponding
`apps/<app>/{views,serializers,urls}.py` files; do not hand-edit either
without checking the current source, since this documentation set is only
trustworthy as long as it matches the code it describes.
