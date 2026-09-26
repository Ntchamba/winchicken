# Winchicken

Poultry farm management for a single farm. Track houses, batches, daily
logs, stock, vaccinations, equipment faults, finance, and SMS alerts —
all in one app.

**Stack:** Django + DRF · React (Vite) · PostgreSQL · Celery + Redis ·
Docker Compose

## Features

- **Onboarding** — create the farm, configure houses and their protocol
  schedules, set stock parameters, add employees.
- **Houses & batches** — protocol templates organized into categories
  (default set + custom, user-defined ones), daily logs, weekly mortality
  and feed-conversion tracking.
- **Stock** — feed, veterinary, equipment and bedding items; movements,
  purchase orders, low-stock thresholds.
- **Finance** — expenses, sales, purchase orders, ROI forecast, batch
  closing reports. Access is role-restricted: full figures for
  Admin/Farm Manager, trend-only for other roles.
- **Alerts & SMS** — event- and schedule-based alert rules, delivered by
  SMS with idempotent, retrying delivery (Celery + Redis).
- **Roles** — Admin, Secondary Admin, Farm Manager, Farmer, Worker,
  Technician, Cashier, each scoped to what they need.

The UI is entirely in French; this document is in English for
contributors.

## Quick start

```bash
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser   # optional, for /admin/ only
```

Open **http://localhost:5173/** and click through to **"Créer une ferme"** — this
creates the single `Farm` row and its administrator account, then walks
you through onboarding (houses/protocol → stock → employees, employees
step skippable). No demo data or credentials are seeded; the account you
create is the first and only one until you add employees.

| Service | URL |
|---|---|
| Frontend | http://localhost:5173/ |
| API | http://localhost:8000/api/ |
| Django admin | http://localhost:8000/admin/ |
| API docs (Swagger UI, JWT required) | http://localhost:8000/api/docs/ |

### If `docker compose up` fails with a permission error

If your user isn't in the `docker` group and you have no sudo access,
set up a **rootless** Docker daemon instead (no root needed, assuming
`docker-ce` + `docker-ce-rootless-extras` are installed):

```bash
export XDG_RUNTIME_DIR=/run/user/$(id -u)
export PATH=/usr/bin:$PATH
dockerd-rootless-setuptool.sh install
```

This starts a per-user `systemd --user` Docker daemon and switches the
CLI to a `rootless` context automatically. Run the setup tool's own
`loginctl enable-linger` command if you want it to keep running without
an active login session.

### If `docker compose up` fails with "port is already allocated"

Something on your machine already uses one of the four host ports (often a
local Redis on 6379). Pick free ones in a `.env` file at the repo root —
the UI's API address and CORS follow automatically:

```bash
WINCHICKEN_DB_PORT=5436
WINCHICKEN_REDIS_PORT=6382
WINCHICKEN_API_PORT=8020     # API then at http://localhost:8020/api/
WINCHICKEN_UI_PORT=5190      # open http://localhost:5190/
```

Run `docker compose up -d --force-recreate` afterwards: a container whose
port publish failed can come back up with no network otherwise.

### Local (non-Docker) backend dev

`backend/.venv` can run Django tooling (`makemigrations`, `test`, etc.)
directly against `backend/.env` (`DB_HOST=localhost`) without the
containers — useful for quick iteration. The containerized `web`/`worker`
services remain the source of truth for how the app actually runs.

Useful commands:

```bash
docker compose logs -f web
docker compose logs -f worker
docker compose exec web python manage.py test
docker compose exec worker celery -A config worker -l info
```

## Configuration

Copy `.env.example` → `.env` in both `backend/` and `frontend/` and
adjust as needed. Notable defaults:

- The `db` service publishes Postgres on host port **5433** (not 5432),
  to avoid clashing with a system-installed Postgres. Inside
  `docker-compose`, `web`/`worker` still reach it at `db:5432` — only
  host-side access (e.g. `psql` from outside the containers) needs 5433.
- `SMS_PROVIDER=console` logs outgoing SMS instead of calling a real
  gateway. Swap in `SMS_PROVIDER`/`SMS_PROVIDER_API_KEY` for a real
  integration — the provider interface is in
  `backend/apps/alerts/providers/base.py`.

## Repository layout

```
backend/    Django project (apps/ — core, houses, batches, stock, maintenance, finance, alerts, protocols)
frontend/   React + Vite app (components/, pages/, api/, context/, styles/, demo/)
docs/       Architecture, data model, API reference, calculations, setup, and deviations log
docker-compose.yml   db (Postgres 16) + redis + web (Django) + worker (Celery) + frontend (Vite)
```

## Running the tests

**Backend** — pytest + pytest-django, one `tests.py` per app under
`backend/apps/*/`. Unit tests (calculations, serializers, the scheduled-alert
time match) and integration tests (full request/response through the DRF test
client against a real Postgres) live side by side.

```bash
# in Docker (matches CI)
docker compose exec web pytest
docker compose exec web pytest apps/alerts -q            # one app
docker compose exec web pytest apps/alerts/tests.py::FireScheduledAlertsTests

# local venv
cd backend && pytest
```

`SMS_PROVIDER=console` (the default) makes the SMS path log instead of calling
a gateway, so the suite never makes a real network call. One-off run of the
scheduled-alert trigger outside Beat: `python manage.py check_scheduled_alerts
[--at HH:MM]`.

**Frontend** — Vitest + React Testing Library, `*.test.jsx` under
`frontend/src/**/__tests__/`. Config (jsdom, `src/test/setup.js`) is in
`vite.config.js`.

```bash
cd frontend
npm test                  # vitest run (CI mode, one pass)
npm test -- --watch       # watch mode
npm test QuickEntryPanel   # filter by filename
```

**CI** — `.github/workflows/ci.yml` runs both on every push and PR: a backend
job (Postgres 16 service → `pytest`) and a frontend job (`npm ci` →
`npm run lint` → `npm test` → `npm run build`), in parallel.

### Regression suite (one command)

`scripts/regression.sh` proves, in a single run, that the whole app still works
after a change — the unit and integration suites **plus** live checks against a
running stack, so a regression that only shows up through the deployed API or in
a real browser is caught too. It re-verifies the FIX 1–7 behaviours and the four
UI items this project has a history of reporting "fixed" while they weren't
(sidebar scroll, factory-reset button, batch-name validation, button alignment).

```bash
# with the verification stack up (winchicken-test on :8010 / :5180)
docker compose -p winchicken-test -f docker-compose.yml -f docker-compose.test.yml up -d
docker compose -p winchicken-test -f docker-compose.yml -f docker-compose.test.yml \
  exec -T web python manage.py migrate

./scripts/regression.sh            # backend + frontend + live API + live UI
./scripts/regression.sh --quick    # skip the long backend suite (fast inner loop)
./scripts/regression.sh --no-ui    # skip the browser checks (no Chrome installed)
```

It exits non-zero if any section fails, and prints a per-section PASS/FAIL
summary. The four parts:

| Part | What it runs | Proves |
|---|---|---|
| Backend | `manage.py test` (unit + `tests_integration_*`) | task completion + stock deduction + **undo**, twice-daily time-slot occurrences, shortfall handling, orphaned assignments — at the ORM level |
| Frontend | `npm test` (vitest) | component logic incl. batch-name validation and submission feedback |
| Live API | `scripts/regression_api.py` | the same FIX behaviours through the running API: farm-local dates, multiple assignees, opening stock, complete/undo |
| Live UI | `scripts/regression_ui.mjs` (headless Chrome over CDP) | the recurring-four + no false "server unreachable" on the stock panel |

Point it at another stack with `REG_API_URL` / `REG_UI_URL` (and
`REG_COMPOSE` for the backend step); credentials via `REG_ADMIN_EMAIL` etc.
The Live UI part is skipped automatically when no Chrome/Chromium is on PATH.

### Smoke test before every deployment (one command, ~15 s)

`scripts/smoke.sh` is the fast sanity check — the critical path only, stopping at
the first broken link. Run it before every deployment; if it fails, do not deploy.

```bash
./scripts/smoke.sh           # API critical path + browser
./scripts/smoke.sh --no-ui   # API only (no Chrome on this machine)
```

| Half | Steps |
|---|---|
| API (`scripts/smoke_api.py`) | app boots (`/api/health/`) → login → dashboard endpoints load → a batch is visible → a task can be completed → stock moves (exactly the line's quantity) → a sale records |
| Browser (`scripts/smoke_ui.mjs`) | SPA boots → the **real login form** logs in → the dashboard renders an active batch → no JS exception and no failed API call |

The API half builds its own throwaway fixture named `SMOKE-<epoch>` (house, batch
starting today, stock item with 10 kg opening stock, one protocol line consuming
2 kg/day), so it does not depend on the farm's data; it deletes the house (which
cascades the batch, line and completion) and then removes the sale and stock item
through `manage.py`. The browser half needs one ACTIVE batch on the farm. Config:
`SMOKE_API_URL` / `SMOKE_UI_URL` / `SMOKE_COMPOSE` (empty = skip DB cleanup) /
`SMOKE_ADMIN_EMAIL` / `SMOKE_ADMIN_PASSWORD` (an Admin or Farm Manager).

## Recent work

- **Scheduled task reminders — made real end to end (2026-08-31):** the trigger from the
  bullet below existed but nothing ran it and no SMS reached the farm. Now: (1) a dedicated
  **`beat` service** in `docker-compose.yml` runs `celery -A config beat`, so
  `check-scheduled-alerts` actually fires every minute (it wasn't — only the worker was
  running); (2) `expand_protocol_to_alert_rules` now creates one `DAILY` `AlertRule` per
  `ProtocolTimeSlot` at that slot's start time (it was hard-coding 08:00 and ignoring the
  configured créneaux); (3) fixed an idempotency-key collision when two protocol lines share
  a créneau; (4) built the **Twilio** SMS provider (`SMS_PROVIDER=twilio`, creds from env),
  with a `TWILIO_TRIAL_TEMPLATE` shim because a *trial* Twilio account rejects custom message
  bodies. Verified live: a slot set to now+3min auto-fired at that exact minute with no manual
  trigger, logged the correctly-worded French reminder, created no duplicate on re-run, and
  (on `SMS_PROVIDER=twilio`) delivered a real SMS. Timezone confirmed `Africa/Douala` (WAT).
  Tolerance window unchanged at 3 minutes. See `docs/deviations.md` Part 23.

- **Time-based trigger for scheduled task reminders (2026-08-30):** `SCHEDULED` `AlertRule`
  rows (`PROTOCOL_TASK`, `WEIGHING_REMINDER`) stored a `trigger_time` but nothing ever fired
  them. New every-minute Celery Beat entry `check-scheduled-alerts` →
  `apps.alerts.services.fire_scheduled_alerts`: for each active `SCHEDULED` rule whose
  `trigger_time` matches the current **farm-local** time and whose schedule says it is due
  today, it creates one `Alert` (which drives the notification bell + the existing Twilio
  `send_sms_task`, with the personalised `apps.alerts.templates` reminder body and recipient).
  Autonomous decisions: (1) new `FARM_TIME_ZONE` setting (env, default `Africa/Douala` / WAT
  — `TIME_ZONE` stays UTC; `trigger_time` is wall-clock the user typed in local time, so a
  bare UTC comparison would fire an hour late); (2) a **3-minute catch-up window** so a brief
  Beat outage doesn't skip a reminder, with a 10-minute per-rule idempotency check preventing
  duplicates (no `Alert` schema change); (3) `ONE_TIME` rules set `active = False` once fired;
  (4) due-today logic reuses `_protocol_line_occurrence` / `weighing_reminder_task` — no
  parallel schedule code; (5) reminders are personal job assignments, so they are **not**
  gated by `NotificationPreference`. Also `python manage.py check_scheduled_alerts [--at HH:MM]`
  for manual/testing runs. See `docs/deviations.md` Part 22.

- **Login screen: wording fix + pre-login farm reset (2026-08-30):** two changes and a set of
  autonomous decisions.
  - **Text.** Every user-facing "Créer la ferme" / "Créez la ferme" is now **"Créer une ferme"**
    (indefinite article) — the `/create-farm` page `<h1>`, its submit button, and its
    `document.title`. *Decision:* also updated the same quoted label where it appears as a
    canonical UI string in `README.md` / `docs/deviations.md`; left it untouched inside
    past-tense changelog prose that is narrating history (e.g. an `api/client.js` comment about
    old landing-page routing) — rewriting those would falsify the record without fixing any UI.
  - **Stale link → reset entry point.** `/login`'s "Créez la ferme" link is **removed** (farm
    creation is permanently closed once a farm exists — `/create-farm` already guards and
    redirects). In its place, a deliberately quiet muted-underline **"Réinitialiser la ferme"**
    link, shown only when `GET /api/farm/exists/` is true. *Decision:* `/login` itself still has
    no hard redirect guard for the no-farm case (the task said none was needed if routing
    already only reaches it with a farm); gating the link on `exists` is enough, and a fresh
    install can't authenticate anyone here anyway.
  - **Pre-login reset flow (works with no session).** Clicking the link opens
    `FactoryResetModal` in a new `mode="pre-login"`: a step-0 "administrator credentials" screen
    (`POST /api/farm/reset/request/`, `AllowAny`) verifies the email + password belong to a real
    `UserRole.ADMIN` on the single farm and returns a **5-minute `django.core.signing` token**
    (HMAC over `SECRET_KEY`, no DB row, no login session) plus the farm name. Every failure —
    unknown email, wrong password, valid credentials for a non-Administrateur — returns the
    identical `"Identifiants invalides."` (400, never 403), with a dummy `set_password` on the
    unknown-email branch to equalise response timing, so an anonymous visitor can't enumerate
    accounts or roles. Step 2 **reuses the existing** explanation + type-the-exact-farm-name
    confirm screens unchanged (only the password field is dropped — already proven in step 0);
    the final action is `POST /api/farm/reset/confirm/` (`AllowAny` — the token is the
    authorisation), which re-opens the token, re-checks the account is still an Administrateur,
    checks the typed name, then runs the **same `apps.core.services.factory_reset_farm`** the
    in-dashboard flow does. The in-dashboard reset (Paramètres → Zone dangereuse, session +
    `IsAdmin` + password) is untouched. *Decisions:* the task's "role `ADMINISTRATEUR`" maps to
    this codebase's `UserRole.ADMIN` (DB value `'ADMIN'`, French label "Administrateur"); token
    TTL 5 min; farm name is learned from the step-1 response, not leaked by `farm/exists/`.
  - **Verified.** 10 new backend tests (`apps/core/tests.py::PreLoginFarmResetTests`) against
    the isolated test DB — token round-trip → full CASCADE wipe, the three indistinguishable
    credential failures, tampered / foreign-salt / expired token, wrong farm name (nothing
    deleted), and that the endpoint needs no auth; full `apps.core` suite green (32 tests).
    `vite build` + `oxlint` clean. The reset itself was **not** run against the live dev stack
    (same rule as Part 12 — that DB holds real between-session farm data and the action is
    irreversible); the `/login` link, the credentials step, and the generic-error path were
    exercised headless. Rationale: `docs/deviations.md` Part 21.

- **Stock restructured like the batch view: dashboard + modal config, custom categories,
  supplier directory, protocol-driven daily consumption (2026-08-28):** `/dashboard/stock`
  is now a dashboard — stock-evolution line charts (running `StockMovement` balance by
  calendar date, `GET /api/farms/{farmId}/stock-evolution/`, a per-item reference line at
  `alert_threshold`) plus a "Fournisseurs" section — with the parameter form moved into a
  "Mettre à jour le stock" modal that reuses `ProtocolEditModal`'s backdrop-blur / focus-trap
  pattern and refreshes the page on save. New `StockCategory` entity (FK from
  `StockItem.category`, four defaults seeded per farm, `+`/`-` tab UI mirroring the protocol
  categories) and `Supplier` entity (`StockItem.supplier` FK, inline "+ Nouveau fournisseur",
  CRUD section). `ProtocolTemplate` rows can now declare `stock_item` + `quantity_per_day`; a
  once-daily Celery Beat task (`apps.stock.services.run_daily_consumption`, idempotent per
  batch/row/date via new `StockMovement.protocol_line`) creates the matching `OUT` movements,
  which feed the existing `LOW_STOCK` mechanism unchanged. The protocol form shows a
  non-blocking "stock insuffisant" warning from `GET /api/stock-items/{code}/coverage/`.
  Autonomous decisions (static `beat_schedule` vs. `django-celery-beat`; `StockCategory.kind`
  discriminator; free-text `PurchaseOrder`/`StockMovement.supplier` migration deferred):
  `docs/deviations.md` Part 20, items 190–197. Plan: `docs/superpowers/plans/2026-08-28-stock-restructure.md`.

- **Live growth curves, quick daily entry, live task propagation, protocol-edit modal
  (2026-08-25):** the global (`/dashboard`) and per-house views now center on day-of-cycle
  weight/survival growth curves (`GET /api/batches/growth-curves/`, one shared
  `GrowthCurves.jsx` component for both the overlaid-all-batches and single-batch scopes) and
  a live "tâches à effectuer maintenant" panel on the house view (`GET
  /api/houses/{houseCode}/tasks-now/`, recomputed from `ProtocolTemplate` on every request,
  never cached). A light quick-entry panel upserts today's mortality/eggs
  (`DailyLog.eggs_collected`, new) without duplicating rows on resubmission. Editing a house's
  protocol now regenerates that house's active batch's scheduled `AlertRule` rows
  (`apps.protocols.services.expand_protocol_to_alert_rules`) — the very first implementation
  of the `ProtocolTemplate → AlertRule` expansion the cahier des charges has described since
  before this build (see `docs/deviations.md` #16/#47); it remains as inert as the project's
  other `SCHEDULED` alert rules pending a Celery Beat schedule (out of scope here — this task
  was about the rows being correct, not about firing them). The "Modifier" protocol-edit entry
  points now open a centered modal (`ProtocolEditModal.jsx`, reusing the landing page's
  `DemoVideoModal` blur/scale pattern) instead of navigating away; the direct
  `/dashboard/houses/{houseCode}/protocol` route still works unchanged as a shareable link.
  Full rationale and autonomous decisions: `docs/deviations.md` Part 6, items 50–59 — including
  that the browser extension wasn't connected this session, so the modal's visuals/blur/focus
  trap were verified by code review only; every backend piece (`AlertRule` regeneration, live
  task recomputation, upsert-not-duplicate quick entry) was verified live against the running
  stack with temporary data cleaned up afterward.

- **Five bugs fixed in the batch-edit flow and sidebar (2026-08-25):** batch renames made
  through the "Modifier" modal now actually persist (new `PATCH /api/batches/{batchCode}/`,
  `name`-only — no such endpoint existed before) and the sidebar refreshes immediately
  (`DashboardShell`'s house/batch fetch is now callable on demand, not just on route change);
  the modal itself now pre-fills from the batch's real current data instead of opening empty;
  the mortality quick-entry field is now large and color-coded by severity (reusing the
  existing `--warning`/`--danger` tokens); the sidebar shows a house's active batch name as
  the primary label instead of the house identifier. Two of the five reported symptoms
  (batch-closing "renaming" the house; the modal "being" the onboarding wizard) did not
  reproduce in the code — audited and documented rather than assumed. Full root-cause notes:
  `docs/deviations.md` Part 7, items 60–68.

- **Branding/polish pass (2026-08-25):** sidebar background now reads the shared `--bg`
  token instead of a hardcoded `#fff` (was already the same color, but could drift); the
  browser tab favicon is now generated from the real Winchicken mark (`logo-mark.png`) —
  the old `favicon.svg` was an unrelated off-brand leftover, not the actual logo; the page
  title is now route-aware via a new `useDocumentTitle` hook called from every top-level
  screen; added meta description/theme-color/Open Graph tags and `lang="fr"`. Full
  decisions (including that "Vite + React" title/favicon were already fixed before this
  task, and the `og:image` root-relative-path decision): `docs/deviations.md` Part 8,
  items 69–73.

- **Sidebar-staleness root-cause fix, batch deletion, backend/frontend reorg (2026-08-25):**
  batch renaming and the sidebar refresh now go through one shared `useHouses()` hook /
  `HousesContext`, and `ProtocolEditModal` refetches it directly on every save — no longer
  dependent on each page remembering to wire a refresh callback (the actual root cause of the
  earlier "fix" being fragile). A real silent-failure bug was also found and fixed: a failed
  save used to leave zero user feedback; it now shows a visible error banner in the modal.
  Added `DELETE /api/batches/{batchCode}/` (Admin/Farm Manager only) with full cascade cleanup.
  `apps/batches` split into a `views/` package + `services.py` (thin views, logic in services —
  see `docs/architecture.md`); `HouseDetailPage.jsx` split into four new single-purpose
  components. A live self-test against the real running stack (not just static checks) caught
  one genuine dev-environment bug a code review and `manage.py check` both missed — see
  `docs/deviations.md` Part 9, items 74-83, including the `Farm.singleton_lock` constraint that
  required freeing the farm slot before the self-test's `/create-farm` step could run.

- **Standing practice, not a one-off:** after implementing a feature, delegate a
  `code-architect` review of the changed files (`.claude/agents/code-architect.md`) before
  considering it done, then actually exercise the change against the live running stack via
  the real API/UI with hand-computed expected values — not just static checks — cleaning up
  any data created for the test afterward. See `docs/deviations.md` Part 9 item 83.

- **Weight entry, sparse growth curve, weighing reminder, `current_count` audit
  (2026-08-25):** the quick-entry panel now logs average weight on any date (not forced to
  today), without clobbering mortality/eggs already recorded for that date — fixing a latent
  bug where blank mortality was previously always forced to 0. The growth curve now shows a
  clear empty state for the weight chart specifically when a batch has no weighings yet,
  independent of whether it has other daily-log data. A new optional "Fréquence de pesée"
  setting drives a recurring reminder through the existing `AlertRule` mechanism (no parallel
  scheduler) and the live "tâches à effectuer maintenant" panel. Separately, `PoultryBatch.
  current_count` is now computed on read (from `initial_count` minus summed `DailyLog.
  mortality`) instead of stored — closes a real gap where a Django-admin edit to a `DailyLog`
  row bypassed both app write paths and left it stale. Full details: `docs/deviations.md`
  Part 10, items 84–87.

- **Weighing entry split into its own section (2026-08-25):** a new `WeighingSection.jsx`
  now handles average weight entry separately from the mortality/eggs quick-entry panel —
  own date field, own card, positioned directly below the growth curves on both dashboard
  locations. The global view requires picking a house/batch before logging a weight (reuses
  the existing selector pattern) and groups the recent-weighings list by house; the
  per-house view stays implicitly scoped, no selector. Purely a frontend reorganization — no
  backend change, the underlying upsert/no-clobber contract is unchanged. Details:
  `docs/deviations.md` Part 11, items 88–90.

- **Farm-wide factory reset, Administrateur only (2026-08-26):** the sanctioned exception to
  this project's standing "no way to delete a farm" rule — `POST /api/farm/reset/`
  (`apps.core.services.factory_reset_farm`) wipes the single `Farm` row and, since every
  farm-scoped table FKs to it with `on_delete=CASCADE` either directly or transitively, that
  one delete cascades through everything: houses, batches, daily logs, stock, vaccinations,
  equipment faults, unusual cases, finance, alert rules/alerts/SMS/notification preferences,
  protocols, and every user account — including the Administrateur who triggered it. Role
  ("Administrateur" only) and password re-verification (`FarmResetSerializer`, checked against
  the real hash, never trusted from the frontend) are both enforced server-side. No separate
  JWT-blacklist step: deleting the `User` rows already makes `JWTAuthentication` reject every
  outstanding access token on its next use, and a refreshed token fails the same way the moment
  it's used — see the service function's docstring. A **plain-text external log** — deliberately
  outside the database, since the database is what's being wiped — records every reset
  (timestamp, admin email/name, farm name) to `backend/logs/factory_reset.log` (git-ignored,
  configured via `settings.LOGGING`'s `factory_reset` logger). The frontend lives on the
  previously-unused "Paramètres" sidebar link (`SettingsPage.jsx`), in a visually separate
  red-tinted "Zone dangereuse" section shown only to Administrateur accounts, behind a two-screen
  `FactoryResetModal` (explanation of everything that will be deleted, then a second screen
  requiring both the exact farm name typed back and the current password before "Réinitialiser
  la ferme" is enabled) — collapsing the task's four described steps into two screens rather
  than four separate clicks, since steps 1 and steps 2–4 naturally group into "read the
  consequences" and "prove it's really you, twice." Also fixed a real, separate bug surfaced
  while implementing this: the shared axios response interceptor's 401-retry path could swallow
  a still-401 response after a "successful" token refresh without ever redirecting (`return
  client(original)` inside a `try` doesn't route that promise's later rejection through the
  `catch` — a JS gotcha, not specific to this feature) and always redirected to `/login`, which
  has no awareness of whether a farm exists; both fixed in `frontend/src/api/client.js` — the
  retry is now awaited so a second 401 reaches the `catch`, and the redirect target is `/`, which
  already re-checks `GET /api/farm/exists/` and shows "Créer la ferme" once a reset has run.
  Verified with a dedicated backend test suite (`backend/apps/core/tests.py`,
  `FactoryResetTests`/`FactoryResetLoggingTests`) run against Django's real, isolated test
  database — one row from every farm-scoped table, confirming the full cascade, the 403 for a
  non-Administrateur caller, the 400 for a wrong password with nothing deleted, and the log
  file's content — deliberately *not* exercised by clicking through the actual running dev
  stack, since that stack's database holds the user's own genuine farm data from real use
  between sessions (see Part 10 item 87's note) and this action is irreversible; full rationale
  in `docs/deviations.md` Part 12, items 91–96.

- **Outage root-caused and fixed, specific error messages, sidebar dark theme, Help link
  (2026-08-26):** the reported "farm creation and login both broken" turned out to be neither
  — the entire backend had been crash-looping since the *previous* task's own factory-reset
  work: the new `LOGGING` config in `backend/config/settings.py` tried to open a `FileHandler`
  on `/app/logs/factory_reset.log`, and Django's dev-server autoreloader crashed on a
  host/container filesystem-permission mismatch the moment it picked up that settings change —
  every request, not just farm creation, had been hitting a dead server since. `GET
  /api/farm/exists/` (checked once the server was actually reachable again) confirmed the real
  farm/user data was completely untouched, so no `docker compose down -v` reset was needed —
  fixed by moving `/app/logs` to a Docker-managed named volume (`docker-compose.yml`) seeded
  with the right ownership by the image build itself (`backend/Dockerfile`), which sidesteps
  host/container uid mismatches on any machine rather than depending on manually-applied
  permissions. Separately, and genuinely responsible for the *generic* error messages hiding
  this: `CreateFarmPage.jsx`'s catch block only ever surfaced an `email` field error before
  falling back to one hardcoded sentence — which is exactly what a total network failure looks
  like from the frontend (`err.response` is `undefined`), and the same brittle
  `err.response?.data?.<one field>?.[0] || "generic"` pattern was copy-pasted into three other
  forms (`EmployeesPage.jsx`, `OnboardingEmployeesPage.jsx`, `HouseProtocolForm.jsx`'s category
  form). Replaced everywhere with a shared `frontend/src/api/errors.js`
  (`getFieldErrors`/`getServerErrorMessage`) that distinguishes an unreachable server, a
  `{detail: ...}` view-level rejection, and per-field serializer validation errors, and shows
  each next to its own input where the form already had per-field slots
  (`CreateFarmPage`/`LoginPage`). Also recolored the dashboard sidebar to a navy/white/mint dark
  theme (base tone sampled directly from `welcome-bg.jpg`, the same image the welcome screen's
  `AnimatedBackground` animates — a still color, not the animated component itself, which has
  no room to read as anything but noise in a 264px column), enlarged the Pesée/quick-entry
  Enregistrer buttons and the "Signaler un cas inhabituel" action (was a barely-visible text
  link; now a full-size warning-toned button), fixed a real button-alignment regression on the
  per-house view ("Modifier le protocole" was inheriting `.add-button`'s `margin-top:18px`,
  meant for an unrelated "add a row" context, and sagging below its `.delete-button` siblings),
  and added an "Aide" sidebar link. Aide links only to
  `docs/protocol-configuration-usage-guide.pdf` (copied into `frontend/public/docs/` so it's
  actually servable, alongside the pre-existing `protocol-configuration.md`) — the two `.docx`
  specification documents in the repo root were read and confirmed to be addressed explicitly
  to the dev team ("Document de référence pour l'implémentation (Claude Code / équipe de
  développement)", "à donner à Claude Code avec ce dernier"), not farm staff, so they are
  deliberately not exposed here. Full rationale: `docs/deviations.md` Part 13, items 97–104.

- **Automated backups, a real test suite + CI, an internal audit log, a richer Cashier screen,
  and employee task assignment (2026-08-26):** five reliability/feature additions landed
  together. **Backups** — `python manage.py backup_db` (`pg_dump -Fc`, timestamped, 7-backup
  retention) and its companion `restore_db <filename>` (typed confirmation required, `--yes` for
  scripted use), both in `backend/apps/core/management/commands/`. Scheduled via a new,
  lightweight `backup` service in `docker-compose.yml` — a plain `sleep`-loop, not real cron
  (nothing in this app needs a specific time of day, only a daily-ish cadence and retention,
  and cron needs a foreground-process wrapper to behave under Docker that a loop doesn't) —
  interval and retention configurable via `BACKUP_INTERVAL_SECONDS`/`BACKUP_RETENTION_COUNT`
  (`.env.example`). Verify with `ls backend/backups/`. The factory-reset confirmation dialog
  now says so explicitly: nightly backups already cover same-day data, and names the manual
  command for extra certainty right before a reset. **Tests + CI** — `pytest`/`pytest-django`
  added (runs the existing Django-`TestCase`-style suite unchanged, since the task named
  `pytest` specifically); new backend tests cover login, the single-active-batch-per-house
  constraint, protocol-save → `AlertRule` regeneration (this exact scenario broke before), the
  `current_count` correction case, and the factory reset/backup paths — 36 backend tests total,
  all passing. Frontend testing didn't exist in this repo at all before this task (checked
  first, per the task's own instruction) — added Vitest + React Testing Library (the standard
  pairing for this Vite project) and wrote the three requested regression tests, including a
  dedicated one pinning down the sidebar-staleness fix (sanity-checked by deliberately
  reintroducing that bug, confirming the test fails, then reverting — see
  `docs/deviations.md`). A `.github/workflows/ci.yml` runs both suites (plus lint and build) on
  every push/PR. **Audit log** — new `AuditLogEntry` model + one shared
  `apps.core.services.record_audit_log()` call site, wired into batch/protocol/employee/
  stock/expense/sale/purchase-order/factory-reset actions, surfaced at `/dashboard/audit`
  (Administrateur only, filterable by action and date). **Cashier** — "Ventes du jour" already
  existed; added a running total and a per-sale "Reçu" button. No PDF library exists anywhere
  in this codebase, so the receipt is a print-styled view (`window.print()`, "Save as PDF"
  covers "downloadable") rather than a new backend dependency. **Task assignment** — an
  optional assignee on protocol-line tasks (`ProtocolTemplate.assigned_to`) and on the
  recurring weighing reminder (`AlertRule.assigned_to`, since that row — unlike the one-shot
  `PROTOCOL_TASK` rows — is actually persistent); an assignee selector on the per-house tasks
  panel (Admin/Farm Manager/Farmer only, matching who can already edit the protocol) with the
  logged-in user's own assignments highlighted, and a new "Mes tâches" view spanning every
  house. Full rationale for every decision, including two premises in the original task that
  didn't match this codebase (feed conversion ratio and the "Réinitialiser" button) and were
  corrected rather than fabricated to match: `docs/deviations.md` Part 15.

- **Farm health score, cycle timeline with milestones, an upcoming-48h widget, and a prominent
  "Cas signalés" incidents view (2026-08-26):** four additive dashboard features. **Farm health
  score** — `GET /api/batches/health-score/` combines three signals into one badge (Bonne/À
  surveiller/Critique) shown near the top of the global view. **The exact tier rules** (see
  `apps.batches.calculations.farm_health_score` for the full docstring):
  - Per active batch: a **mortality breach** is the latest week's mortality % exceeding
    `MORTALITY_REFERENCE_RANGE[1] / (number of weeks so far)` — the *exact same pro-rata
    formula* `WeeklyKpiCharts.jsx` already uses to color a week's bar red, reusing the same
    `MORTALITY_REFERENCE_RANGE` constant rather than a new hardcoded number. A **FCR breach** is
    the latest feed-conversion ratio exceeding `FCR_REFERENCE_RANGE[1]` (2.30).
  - Farm-wide: the count of open `Alert` rows (`status != RESOLVED`), and whether any of them
    has `severity='danger'`.
  - **Critique**: 2+ batch breaches total, OR any open danger-severity alert.
  - **À surveiller**: exactly 1 batch breach, OR at least 1 open alert (any severity).
  - **Bonne**: none of the above.

  (The original task named `MORTALITY_SPIKE`/`WEIGHT_DEVIATION` alert types to check for —
  neither exists in this codebase's `AlertRuleType`; the real, automatically-fired types are
  only `LOW_STOCK` and `CONSUMPTION_DEVIATION`. The mortality/FCR breach signals are computed
  directly instead, which is what the task's own item 1 asked for as the first two signals
  anyway.) **Cycle timeline** — the per-house view gets a horizontal timeline (start/current/end
  markers, a tick per upcoming `ProtocolTemplate` milestone, click/hover tooltip, past milestones
  muted) from a new `GET /api/houses/{houseCode}/milestones/`, itself the same
  `compute_cycle_milestones` function the **upcoming-48h widget** (global view, `GET
  /api/tasks/upcoming/`) filters to the next 2 days across every house — one computation, two
  views, per the task's own "reuse... not a separate calculation" instruction. No
  `ProtocolTimeSlot`/time-of-day concept exists anywhere in this codebase (checked before
  assuming the task's "exact time window if slotted" premise was real) — every entry is a
  day-level "aujourd'hui"/"demain" label. **"Cas signalés"** — a new, prominent, color-coded
  incidents panel (large cards, count badge, `--danger`/`--warning` treatment) shown on both the
  global view (farm-wide) and the per-house view (scoped) — literally the same component either
  way. `UnusualCase` had no resolution concept at all before this task (added `resolved`/
  `resolved_at`); `EquipmentFault` already had a free-text `status` field but no endpoint to
  change it (added one). Resolving removes an item from this view but only flips a field —
  nothing is deleted, and both resolve actions log to the audit trail (`/dashboard/audit`). No
  photo field exists anywhere on either model (checked before assuming the task's "photo if one
  was attached" premise was real) — omitted. Full rationale for every decision:
  `docs/deviations.md` Part 16.

- **Civility field + personal task-reminder SMS.** Added `User.civility` (M/Mme,
  required on both account-creation forms — "Créer une ferme" and the
  employee form, onboarding step 3 and `/dashboard/employees`). Existing
  accounts from before this migration backfill to `M` (a model-level default,
  not a null) so the reminder template never renders with a missing civility;
  an admin can still correct any account afterward via the employee-edit form.
  Added a new `apps.alerts.templates` module with the personal
  `"Bonjour {civility} {name}, merci d'effectuer {task}..."` template for
  `SCHEDULED`/`PROTOCOL_TASK` reminders — targets the task's assigned employee,
  falling back to the batch's Fermier, never broadcasting to the whole farm.
  `ProtocolTimeSlot` (new model, didn't exist before) lets a protocol line carry
  one or more times of day, each producing its own correctly-timed reminder; a
  line with none renders "...aujourd'hui" instead. The existing `EVENT`-type
  alert templates (`LOW_STOCK`, `CONSUMPTION_DEVIATION`, ...) were deliberately
  left untouched, inline in `apps.alerts.services` — not moved into the new
  module, since doing so would edit code this task's own rules said not to
  touch. No Beat-triggered dispatch was added for this reminder type — no
  `SCHEDULED` `AlertRule` has ever actually fired automatically in this codebase
  (no Celery Beat schedule configured, a pre-existing gap), and wiring that up
  was explicitly out of scope ("don't touch the SMS sending/retry/idempotency
  mechanism"). Full rationale: `docs/deviations.md` items 152–156.

- **Five fixes from live testing feedback.** **Bug 1** ("Horaires" missing from
  "Modifier"): root cause was two-fold, not a data problem — the model/migration
  were already applied, but the serializer never exposed `time_slots` and the
  shared `HouseProtocolForm.jsx` row component never rendered a "Horaires"
  section at all. Both fixed; `ProtocolTimeSlot` also gained an `end_time` field
  (a "07h00–09h00" window, not a single point) to match the requested chip/
  two-time-picker UI — the SMS reminder template is unchanged and still fires at
  `start_time` only. **Bug 2** (Administrateur blocked from recording weight/
  mortality): `DailyLogQuickEntryView`/`DailyLogListCreateView` used an
  `IsFarmerOrWorker` check that wrongly excluded Admin and Farm Manager — a
  genuine regression, fixed by widening to `IsAdminOrFarmManagerOrFarmerOrWorker`
  (Technician/Cashier deliberately left out — not their role). **Bug 3**
  (calendar missing multi-day protocols): the calendar read `PROTOCOL_TASK`
  `AlertRule` rows, which are only ever generated for a line's first due day —
  fixed by computing the month view directly from `ProtocolTemplate` + each
  house's active batch, reusing the exact day-in-range check the "tâches à
  effectuer maintenant" panel already uses (extracted into a shared helper so the
  two can't drift apart). **Feature 4** (any role assignable): the assignee
  dropdown reused the Admin/Secondary-Admin-only, self-excluding `/api/
  employees/` endpoint — replaced with a purpose-built `/api/tasks/
  assignable-users/` open to whoever can actually assign, listing every role
  including the assigner's own account. **Feature 5** (controlled case
  resolution): cases already defaulted to unresolved (verified, not changed).
  `UnusualCaseResolveView` narrowed to Admin/Farm Manager only (Farmer no longer
  resolves its own reports); `EquipmentFaultResolveView` deliberately kept at
  Technician/Admin, per the cahier des charges' own permission matrix — a
  disclosed judgment call, not an oversight. Added `resolved_by` to both models
  and a "Historique" tab inside the existing `IncidentsPanel` component (not a
  new route) showing who resolved each case and when. Full rationale for every
  decision: `docs/deviations.md` items 157–166.

- **Sidebar rename, alert pulse treatment, phrasing audit.** Renamed the
  sidebar's "+ Nouveau bâtiment" to "+ Nouvelle bande" — it already matched
  an existing "Nouvelle bande" quick-action on the dashboard home that
  routes to the exact same onboarding flow, so this also fixes a real
  terminology inconsistency, not just relabels. Added a smooth "needs
  attention" pulse (`.pulse-alert` in `dashboard-theme.css`) to the
  notification-bell badge, the "Cas signalés" section/badge, and a new
  sidebar open-cases badge (didn't exist before — built it, since it was
  one of three explicit targets). **Accessibility note, so this isn't
  re-litigated later:** this is deliberately a smooth opacity/glow pulse at
  1.3s per cycle (~0.77Hz), not a hard on/off flash — rapid flashing above
  roughly 3Hz is a documented seizure trigger for photosensitive users
  (WCAG 2.3.1), not a style call. `prefers-reduced-motion: reduce` disables
  the animation entirely in favor of a static highlighted ring; verified
  via `getComputedStyle` in a real browser under both settings. Every
  pulsing badge only renders while its count is actually nonzero, so it
  stops on its own once resolved/read — no separate on/off logic needed.
  Also swept every listed screen for phrasing issues: found no `bande`/`lot`
  inconsistency (already consistent), but did find two leftover-English
  default strings (`"Main store"` in `StockParametersForm.jsx` and
  `OnboardingContext.jsx`, pre-filling "Nom de l'entrepôt" with English on
  first load — same class of bug as the earlier "POULET À VOIE" fix) and one
  factually self-contradicting empty state (`HomeDashboard.jsx` said "1
  bâtiment configuré" while rendering exactly when there are zero). Full
  before/after list and rationale: `docs/deviations.md` items 170–174.

- **"+ Nouvelle bande" wizard-shell leakage, deeper diagnosis + multi-batch
  onboarding.** Root cause confirmed live (headless-browser screenshot of the
  actual broken state) before writing any fix, per this task's own "prove it,
  don't reason about it" instruction: `OnboardingLayout.jsx` — the shell
  wrapping every onboarding route — didn't know about `isAddingHouse` at all
  (that flag only ever lived inside `OnboardingProtocolPage.jsx`), so adding a
  batch to an already-configured farm still showed the full 3-step wizard
  chrome (steps it never reaches) and a "back to the marketing landing page"
  link for an already-logged-in user. Fixed the shell itself to read the same
  flag: add-house mode now shows neither the step list nor the old back link,
  just "Retour au tableau de bord." Also fixed the save button's own stale
  "Suivant" label (→ "Créer la bande") — same class of bug as the earlier
  sidebar rename, just one layer deeper. Added multi-batch creation for *true*
  first-time onboarding: an "Ajouter ce bâtiment et en configurer un autre"
  button lets a new farm's signup configure several houses in one pass
  (reuses the existing single-house submission endpoint, called once per
  house, with a running "already configured" list and a way to move on
  early) — the single-house "+ Nouvelle bande" shortcut deliberately doesn't
  get this button, staying a one-house action. The multi-batch flow couldn't
  be verified against the live dev stack (this app is single-farm; the one
  real farm running already carries real test data a factory reset would
  destroy just to get an unconfigured user) — verified instead with a new
  `OnboardingProtocolPage.test.jsx` exercising the real component tree.
  Full rationale: `docs/deviations.md` items 175–177.

- **Purchase orders — creation, receiving, and its stock link.** More of the
  backend already existed than the task assumed (`PurchaseOrder` model,
  serializer, and views, from an earlier task) — audited it against every
  explicit requirement instead of rebuilding, and fixed the real gaps found:
  creation/receiving was missing Farm Manager from its allowed roles (now
  Admin/Farm Manager/Cashier, this task's own list); the generated
  `StockMovement` was silently dated to the *order* date instead of the
  actual receiving date (verified live with a backdated order); nothing
  stopped a finalized order from being un-received or un-cancelled, so that's
  now rejected server-side; and the receiving transition is now wrapped in a
  transaction. One requirement genuinely can't be met without a schema
  change this task's own rules forbid: `order_date` is `auto_now_add` at the
  model level, so "editable" isn't possible — the creation form shows it as
  a disabled, today-filled field instead of pretending otherwise. Added an
  optional supplier-batch-number input at receiving time. New standalone
  `/dashboard/purchase-orders` screen (not a Stock tab — `StockParametersForm`
  is already a self-contained item-configuration editor, and this is a
  different concern), with a small from-scratch item picker (no existing
  "select a StockItem" pattern was found to reuse). Verified the entire loop
  live end-to-end: create → appears PENDING → receive with a batch number →
  RECEIVED, correct `StockMovement` confirmed via shell, stock quantity
  confirmed increased; second order created and cancelled → CANCELLED, no
  movement created; a Farmer account confirmed blocked both in the UI
  (sidebar link absent, controls hidden) and server-side (403). Full
  rationale: `docs/deviations.md` items 178–184.

- **Finances restructured into one page; new Salaires (payroll) module.**
  "Finance" is "Finances" everywhere now, and the sidebar link is an
  accordion revealing four sub-items — Ventes / Achats / Salaires / Globale
  — all on a single route (`/dashboard/finances`); clicking a sub-item is a
  smooth in-page scroll to `#<section>`, never a route change. Ventes/Achats
  are new bucketed evolution views (`sales-evolution`/`purchases-evolution`,
  week/month/year toggle, same full-vs-restricted access split as the rest
  of Finance); Achats is read-only aggregation of received purchase orders
  + expenses, no new data entry. Closed a real gap the task called out: the
  Cashier screen (`/dashboard/cashier`) had no way to record a general
  expense — added a small "Enregistrer une dépense" form there. New payroll
  module: `User.hourlyRate`, `WorkHoursEntry` (self-reported, or logged by
  Admin/Farm Manager on an employee's behalf), `SalaryPayment` (rate/hours
  snapshotted at calculation time so a later rate change can't retroactively
  change a past payment) — calculation is a manual "Calculer les salaires du
  mois" button, not a scheduled task (this codebase has no Celery Beat
  schedule anywhere yet, and a monthly figure a human reviews before
  "Marquer comme payé" anyway doesn't need one). Marking a payment paid
  creates a matching LABOR `Expense` in the same transaction, feeding
  "Main-d'œuvre" into Achats/Globale. Salaires is hidden entirely (not just
  restricted) for anyone but Admin/Farm Manager, enforced server-side —
  live verification caught that the sidebar itself still listed the
  "Salaires" sub-item for every role even though the section content was
  correctly gated, fixed with a `canSeeSalaires` prop matching this
  codebase's existing `canSee*` pattern. Also caught and fixed live: since
  all four sections mount together on one page, "Marquer comme payé"
  (which happens inside that same page) left Achats/Globale showing stale
  totals until a full reload — fixed with a small version counter that
  forces those two sections to refetch. Farm Manager has no
  `/dashboard/employees` access (unchanged), so hourly-rate editing is
  additionally available inline in the Salaires section itself, not only on
  the Employees page. Verified live end-to-end (sale + expense → Ventes/
  Achats; rate + hours + calculate + pay → correct amount, LABOR expense,
  Main-d'œuvre in Achats; non-Admin/Farm-Manager role confirmed unable to
  see Salaires in the menu or the page). Full rationale:
  `docs/deviations.md` items 185–189.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — system overview
- [`docs/data-model.md`](docs/data-model.md) — entities and relationships
- [`docs/api-reference.md`](docs/api-reference.md) — endpoint reference
- [`docs/calculations.md`](docs/calculations.md) — KPI/finance formulas
- [`docs/setup.md`](docs/setup.md) — detailed setup notes
- [`docs/protocol-configuration.md`](docs/protocol-configuration.md) — protocol categories & batch naming
- [`docs/deviations.md`](docs/deviations.md) — every place the implementation departs from or extends
  the original spec, with rationale, kept up to date as the authoritative log
