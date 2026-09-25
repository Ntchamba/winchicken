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
- **`apps.stock`** — `StockCategory` (per-farm, four seeded defaults +
  custom, via `signals.py`), `Supplier` (directory), `StockItem` (item
  definitions; `category`/`supplier` FKs), `StockMovement` (IN/OUT — on-hand
  quantity always derived, never stored; `protocol_line` marks auto-generated
  rows), `Vaccination`. `calculations.py` holds `current_quantity`,
  `stock_evolution`, `coverage_for`; `services.py` holds
  `run_daily_consumption` (the protocol-driven daily deduction, wired to a
  once-daily Celery Beat schedule in `config/celery.py` — the project's only
  Beat entry — and to `manage.py run_stock_consumption`).
- **`apps.maintenance`** — `EquipmentFault`, `UnusualCase`. The smallest app:
  declare-and-list only, no status-transition endpoints (see
  `docs/deviations.md`).
- **`apps.finance`** — `Expense`, `Sale`, `PurchaseOrder`, plus
  `calculations.py` (cash-on-hand, pending payables, ROI forecast, monthly
  summary, expense-category breakdown, break-even/safety-margin helpers —
  the last two are implemented but not wired to any endpoint).
- **`apps.alerts`** — `AlertRule`, `Alert`, `SmsMessage`,
  `NotificationPreference`, plus the async SMS pipeline: `services.py`
  (`trigger_alert`, `check_low_stock`, `check_consumption_deviation`),
  `signals.py` (wires `StockMovement`/`DailyLog` `post_save` to those
  checks), `tasks.py` (`send_sms_task`, the Celery task with idempotency +
  exponential backoff), `providers/` (pluggable SMS gateway interface,
  `console` provider for local dev).

## OpenAPI schema

`drf-spectacular` is wired into `backend/config/settings.py`
(`INSTALLED_APPS`, `REST_FRAMEWORK['DEFAULT_SCHEMA_CLASS']`,
`SPECTACULAR_SETTINGS`) and `backend/config/urls.py`:

- `GET /api/schema/` — raw OpenAPI 3.0 document (`SpectacularAPIView`).
- `GET /api/docs/` — Swagger UI (`SpectacularSwaggerView`).

Neither view sets its own `permission_classes` directly, but
drf-spectacular's `SpectacularAPIView`/`SpectacularSwaggerView` default
their own permissions to `AllowAny` internally regardless of
`REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES']` — this was caught by live
testing (both endpoints returned `200` unauthenticated) and fixed by
setting `SPECTACULAR_SETTINGS['SERVE_PERMISSIONS'] =
['rest_framework.permissions.IsAuthenticated']` explicitly (see
`docs/deviations.md` item 24). Both now correctly require a JWT.

```bash
cd backend && .venv/bin/python manage.py spectacular --file /tmp/winchicken-schema-check.yaml
```

produces the schema with **0 warnings and 0 errors**. This has been run
against the live containerized stack: `GET /api/docs/` and
`GET /api/schema/` both return `401` unauthenticated and `200` with a valid
JWT, confirmed directly against the running `web` container.

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

## Code organization conventions (established 2026-08-25, `apps/batches` + dashboard frontend)

Adopted for `apps/batches` and the dashboard-adjacent frontend pieces during the sidebar-fix/
batch-deletion task (`docs/deviations.md` Part 9); not yet retroactively applied to every other
app/page — apply it incrementally to a file the next time you're already touching it for an
unrelated reason, per that task's own scoping rule, rather than as a standalone sweep.

**Backend:**
- Views/viewsets stay thin — parse the request, check permissions, call a service, shape the
  response. Anything with more than one DB write or non-trivial computation belongs in a
  `services.py` per app (see `apps/batches/services.py`, `apps/protocols/services.py`).
- Serializers handle shape/validation only. A serializer that needs real logic beyond a
  one-line `validate_*`/`create`/`update` is a sign the logic belongs in `services.py` instead.
- Once a single `views.py` covers more than one clearly distinct resource, split it into a
  `views/` package by resource (e.g. `apps/batches/views/{batches,daily_logs,kpi}.py`), with
  `views/__init__.py` re-exporting every class so existing `from apps.<app> import views` /
  `views.XxxView` call sites in `urls.py` need no changes.

**Frontend:**
- A component crossing ~200-250 lines, or mixing data-fetching + form state + modal chrome +
  validation, gets split: data-fetching into a small hook (`useHouses()` — `{data, loading,
  error, refetch}`), single presentational pieces (a card, a row, a chart) into their own file
  under `components/`, page-level composition staying in `pages/`.
- State genuinely shared across sibling parts of the tree (not just parent→child props) goes
  through a small Context (`context/HousesContext.jsx`), not a callback threaded through
  `useOutletContext()` at every call site — that pattern is easy to wire correctly once and
  forget on the next new consumer (see `docs/deviations.md` Part 9 item 74 for the bug that
  came from exactly that).
- API calls stay centralized in `api/endpoints.js`, never inline `axios`/`fetch` in a component.
- Repeated UI patterns (a destructive-action confirm card, previously duplicated three times)
  get pulled into a shared component (`components/ConfirmDialog.jsx`) rather than a fourth copy.

## Scale: pagination, cache, background jobs (2026-09-25 load test)

Measured with `backend/scripts/load_test.sh` (`seed_load_farm` + `bench_load`, `*_load` databases
only); `apps/core/tests_query_scaling.py` keeps per-row queries from coming back.

- **Pagination.** Every list endpoint pages by 20 through `apps.core.pagination.
  StablePageNumberPagination`, which appends the primary key to the view's ordering — tied
  dates otherwise let a row appear on two pages and another on none. On the frontend, a short
  reference list is read in full with `api/pagination.js` `fetchAllPages`; a list that only grows
  (employees, alerts, incident history, salary payments) uses `hooks/usePagedList.js` +
  `components/LoadMoreButton.jsx` ("Afficher plus", "N sur M affichés"). Reading page 1 only is
  the bug this replaced — it hid the 21st employee.
- **Response cache.** `apps/core/cache.py`: `@cached_farm_response` on the "Bilan global" tree,
  the health score and the growth curves — 30 s in the `responses` cache (Redis), keyed by a
  farm-wide data version + the farm-local date. The version is bumped after commit by any model
  save/delete/m2m change (signals, so Celery writes count) and by any successful unsafe request
  (`InvalidateOnWriteMiddleware`, which catches `update()`/`bulk_create`). Unreachable Redis =
  no cache, never an error. Switched off (DummyCache) under the test runner; `tests_cache.py`
  switches it on.
- **Background import.** The employee Excel import is a Celery job — see
  `docs/excel-import.md`. The job's state, and nothing else, uses the `default` cache.
- **Calendar.** `GET /api/protocols/schedule/?month=&view=summary` (per-day count + the pills a
  cell shows) and `?date=` (one day) are both cut from `compute_month_schedule`; the flat month
  was 4.4 MB at 50 houses.
- **Assignee picker.** `GET /api/tasks/assignable-users/?q=&limit=`; `AssigneePicker` searches
  instead of downloading every account.

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
