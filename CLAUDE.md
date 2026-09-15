# Winchicken
> Claude Code config — poultry farm management, single farm, local deployment

## Role
- Senior full-stack & DevOps. Ultra-concise, direct answers, zero fluff, code first.

## What this is
Farm management software for **one** poultry farm in Cameroon, run on the farm's own machine.
Not SaaS, not multi-tenant: `apps.core.models.Farm` is a DB-enforced singleton
(`singleton_lock` unique constant), there is no signup, and the first account is created
through the landing page's "Créer la ferme" flow. No seed data or demo credentials exist.

Day-to-day use is a worker on a phone recording what happened in a poultry house: daily logs
(mortality, feed, water, eggs), weighings, protocol tasks marked done, incidents, stock,
sales and expenses.

## Architecture decisions it is built on
- **Single farm, local deployment.** Every query is farm-scoped through `request.user.farm`;
  there is no tenant dimension to design for.
- **French UI, always.** Every user-facing string, label, error and button is French. Code,
  comments, commits and docs are English.
- **FCFA (XAF).** `frontend/src/utils/money.js` — whole numbers, space-grouped thousands, unit
  always shown. Bare numbers are counts ("954 volailles"), never money.
- **Farm-local time (`Africa/Douala`).** `FARM_TIME_ZONE` drives `TIME_ZONE` and
  `CELERY_TIMEZONE`; `USE_TZ` stays True and containers set `TZ` to match. Always
  `timezone.localdate()` on the backend and `todayISO()` from `utils/localDate.js` on the
  frontend — never `timezone.now().date()` or `toISOString().slice(0, 10)`, which are UTC and
  mis-date every entry made in the first hour after local midnight.
- **Stock moves only on an explicit user action.** Completing a protocol task occurrence
  ("Marquer comme fait") or executing a composition. There is deliberately no automatic
  deduction in `beat_schedule` — the 2026-08-28 daily task was removed on 2026-08-31.
- **Task occurrences are `(protocol line, batch, date, time_slot)`.** A line with
  `ProtocolTimeSlot` rows is one task *per slot* — twice-daily feeding deducts twice.
- **7 roles** (`UserRole`): ADMIN, SECONDARY_ADMIN, FARM_MANAGER, FARMER, WORKER, TECHNICIAN,
  CASHIER. Each `User` gets a class-table-inheritance profile row; permissions go through
  `apps.core.permissions`.

## Stack
- **Backend**: Django + DRF, JWT (SimpleJWT), drf-spectacular
- **Frontend**: React + Vite (`npm run lint` is oxlint, `npm run test` is vitest)
- **DB**: PostgreSQL · **Async**: Celery + Redis · **Infra**: Docker Compose, Linux
- Docker on the dev machine is **rootless**: host uid 1000 maps to container uid 0, so a
  bind-mounted path is root-owned inside the container. Anything the app must write goes in a
  named volume (see `winchicken_backend_logs`).
- SMS/alerts: `apps/alerts/providers/` — `console` by default, `twilio` available.

## Structure
- `backend/apps/` — core, houses, protocols, batches, stock, maintenance, finance, alerts,
  search
- `backend/apps/<app>/services.py` — business logic; views stay thin
- `backend/apps/stock/consumption.py` — the only protocol-driven stock deduction path
- `backend/config/` — settings, urls, celery
- `frontend/src/` — api/, components/, context/, hooks/, pages/, routes/, styles/, utils/
- `docs/architecture.md` — the codebase as it actually is
- `docs/deviations.md` — every point where the build diverges from the two `.docx` specs, with
  the incident that caused it. Read it before assuming a surprising choice was an accident.

## Critical rules
- No business logic in views or in JSX; it lives in `services.py` / hooks.
- Celery tasks take serializable arguments only (IDs, never model instances).
- Two paths computing the same thing is how this codebase has broken before (sidebar
  staleness, the calendar, task slots). Reuse the existing helper; never write a second copy.
- **When a delete-and-recreate becomes an upsert, the code that was compensating for the
  deletion becomes a bug.** FIX 3.5 turned the stock PUT into an upsert and the stock instantly
  doubled: `api/stockSave.js` had been re-posting each row's whole quantity to rebuild a level
  the `delete()` kept wiping. Before changing how a collection is persisted, find every caller
  that was working around the old behaviour.
- Before replacing a collection, check `on_delete` on **everything** pointing at it — via
  `model._meta.related_objects`, not grep, which misses multi-line FK definitions. A CASCADE two
  hops away (`ProtocolTimeSlot` -> `TaskCompletion`) is still a silent deletion, and re-creating
  a row with the same primary key does **not** restore a FK that `SET_NULL` already cleared.
- Secrets via env / Docker secrets, never hardcoded.
- Docker: multi-stage images, non-root user, healthchecks.
- Nothing that runs at settings-import time may raise — it crash-loops the container with no
  server and no error page.

## Code style
- Python: type hints, early return, docstrings that say *why*, not *what*.
- React: function components and hooks.
- Commits: Conventional Commits (`feat:`, `fix:`, `chore:`…), one concern per commit.

## Key commands
```bash
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py test
docker compose logs -f worker

# isolated verification stack — DB winchicken_test, API :8010, UI :5180
docker compose -p winchicken-test -f docker-compose.yml -f docker-compose.test.yml up -d
docker compose -p winchicken-test -f docker-compose.yml -f docker-compose.test.yml \
  exec -T web python manage.py seed_test_farm   # refuses any DB not ending in _test
```

## Expected response format
- Code first, explanation after (1-2 lines if needed). No reframing, no filler disclaimers.

## Verification gate for UI / behavioral fixes

This project has a documented history of fixes reported as complete that weren't (sidebar
scrolling, factory-reset button, batch validation, scheduled notifications). Before any UI or
behavioral fix is reported to the user as complete — especially in an area that has previously
been reported fixed and recurred — hand it to the `qa-verifier` subagent via the Task tool.

- `qa-verifier` verifies against the live running app through the connected Chrome extension
  (computed CSS, real network requests, rendered DOM, console) — never from source alone. It
  returns a pass/fail verdict with concrete observed evidence and cannot edit code.
- A `PostToolUse` hook (`.claude/hooks/post-edit-verify.sh`, see its README) already runs the
  frontend build + lint (+ the related test file) on every `.css`/`.jsx`/`.tsx` edit; the
  `qa-verifier` gate is the behavioral complement to that build-level gate.
