# Setup

Commands below are exactly the ones documented in the root `README.md` — nothing here is
invented; if a command isn't in the README, it isn't listed here as a "standard" way to run
the project either.

## Run it (Docker — primary path)

```bash
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser   # optional, for /admin/ only
```

This has been run end-to-end against the actual stack (all 5 containers healthy;
farm creation → onboarding → employee login → daily logs → finance → batch closing
all exercised live), then the database was flushed back to empty. If `docker compose
up` fails with a permission error and there's no `docker` group membership or sudo
access available, see the root `README.md`'s "If `docker compose up` fails with a
permission error" section — a rootless Docker daemon (already-installed
`docker-ce-rootless-extras` package, no root needed) is a working fallback and is
what this build actually ran on.

Then open **http://localhost:5173/** and click **"Create the farm"** — this creates the
single `Farm` row and its administrator account (`POST /api/farm/create/`), then walks
through onboarding (houses/protocol → stock → employees, employees step skippable). **No
demo credentials are seeded** — the first account is whichever one you create through that
flow; `createsuperuser` above is optional and only grants access to Django's `/admin/`, not
a dashboard login.

- Frontend: http://localhost:5173/
- API: http://localhost:8000/api/
- Django admin: http://localhost:8000/admin/

Useful commands:

```bash
docker compose logs -f web
docker compose logs -f worker
docker compose exec web python manage.py test
docker compose exec worker celery -A config worker -l info   # already the worker's default command
```

`docker-compose.yml` runs 5 services together: `db` (Postgres 16), `redis`, `web` (Django,
port 8000), `worker` (Celery, `celery -A config worker -l info`), and `frontend` (Vite dev
server, port 5173). The `db` service maps container port 5432 to **host port 5433**
(`"5433:5432"` in `docker-compose.yml`) — deliberately not 5432, to avoid clashing with a
system-installed Postgres that may already own 5432 on the host machine. This host-side
5433 mapping only matters when connecting to the dockerized `db` from *outside* the compose
network (e.g. `backend/.venv` tooling below); `web`/`worker` reach it at `db:5432` internally
regardless, via the container-network hostname `db`.

### Regenerating the OpenAPI schema / API docs

```bash
docker compose exec web python manage.py spectacular --file /tmp/winchicken-schema-check.yaml
```

or, from `backend/` with the local venv (below), without needing the containers running.
Swagger UI is served at `GET /api/docs/` and the raw schema at `GET /api/schema/` — both
require a JWT access token like every other endpoint (see `docs/architecture.md`).

## Local (non-Docker) backend dev

A `backend/.venv` is also set up for running Django tooling directly (`makemigrations`,
`test`, etc.) without the containers, pointed at `backend/.env` (`DB_HOST=localhost`,
`DB_PORT=5433` — matching the host-side port mapping above, so this only works while the
dockerized `db`/`redis` services are up via `docker compose up -d db redis` or the full
stack). Handy for quick iteration; the containerized `web`/`worker` services are the source
of truth for how the app actually runs.

```bash
cd backend
.venv/bin/python manage.py migrate
.venv/bin/python manage.py test
.venv/bin/python manage.py spectacular --file /tmp/winchicken-schema-check.yaml
```

## Environment variables

### `backend/.env` (from `backend/.env.example`)

| Variable | Default | Notes |
|---|---|---|
| `SECRET_KEY` | `change-me-in-production` | Django secret key |
| `DEBUG` | `True` | |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | comma-separated |
| `DB_NAME` | `winchicken` | |
| `DB_USER` | `winchicken` | |
| `DB_PASSWORD` | `winchicken` | |
| `DB_HOST` | `localhost` | `db` inside `docker-compose.yml`'s `web`/`worker` services |
| `DB_PORT` | `5433` | `5432` inside `docker-compose.yml`'s `web`/`worker` services — see the port-mapping note above; only the host-side `.env.example` uses 5433 |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | comma-separated |
| `REDIS_URL` | `redis://localhost:6379/0` | `redis://redis:6379/0` inside `docker-compose.yml` |
| `SMS_PROVIDER` | `console` | logs SMS instead of sending; see `apps/alerts/providers/` |
| `SMS_PROVIDER_API_KEY` | *(empty)* | never hardcoded — real provider integrations must read this |
| `SMS_PROVIDER_SENDER_ID` | `WINCHICKEN` | |

`docker-compose.yml` sets its own equivalent environment block per service (`web`,
`worker`) rather than reading `backend/.env` directly — the two are meant to stay in sync,
`backend/.env` being for the local `.venv` path and the compose file's inline `environment:`
block being for the containerized path.

### `frontend/.env` (from `frontend/.env.example`)

| Variable | Default | Notes |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8000/api` | consumed in `frontend/src/api/client.js` via `import.meta.env.VITE_API_URL` |

## First-account creation flow (no seeded credentials)

There is no seed data, fixture, or demo account anywhere in this codebase — `GET
/api/farm/exists/` is what the landing page (`frontend/src/pages/LandingPage.jsx`) calls to
decide whether to show "Create the farm" or "Log in", and the very first account is created
through that flow:

1. Land on `/` → landing page checks `GET /api/farm/exists/` (public, `AllowAny`).
2. If no farm exists yet, click "Create the farm" → `/create-farm`
   (`frontend/src/pages/CreateFarmPage.jsx`) → `POST /api/farm/create/` with
   `{ admin_name, email, password, farm_name }`. This creates the single `Farm` row and one
   `User` with `role=ADMIN` (+ its `Admin` role-subtype row) in one transaction
   (`apps.core.serializers.FarmCreateSerializer.create`), then immediately returns a JWT pair
   exactly like `POST /api/auth/login/` would (`is_configured: false`, `role: "ADMIN"`).
   A second `POST /api/farm/create/` is rejected with `409` once a farm exists — enforced
   server-side (`apps.core.views.FarmCreateView.create`), not just hidden client-side.
3. The frontend is redirected into onboarding (`/onboarding/protocol` →
   `/onboarding/stock` → `/onboarding/employees`, the last step skippable per cahier des
   charges 5.3) because `is_configured` is `false` (see `docs/architecture.md`'s
   "`is_configured` onboarding gate" section).
4. Onboarding step 1 posts to `POST /api/protocols/onboarding/`, creating the first
   `PoultryHouse` + `ProtocolTemplate` lines (+ optionally the first `PoultryBatch`).
   Onboarding step 2 posts to `PUT /api/farms/{farmId}/stock-items/`, creating the first
   `StockItem` rows. Once both exist, `is_farm_configured()` flips to `true`
   (`apps.core.services.is_farm_configured`) and subsequent logins land on `/dashboard`
   instead of being redirected back to onboarding.
5. Any further accounts (Farm Manager, Farmer, Worker, Technician, Cashier, Secondary Admin)
   are created by the Admin (or Secondary Admin) through `/dashboard/employees` →
   `POST /api/employees/` — never through `/api/farm/create/`, which only ever creates the
   one Admin account per farm.

## `manage.py test`

```bash
docker compose exec web python manage.py test
# or, locally:
cd backend && .venv/bin/python manage.py test
```
