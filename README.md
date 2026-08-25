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

Open **http://localhost:5173/** and click **"Créer la ferme"** — this
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

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — system overview
- [`docs/data-model.md`](docs/data-model.md) — entities and relationships
- [`docs/api-reference.md`](docs/api-reference.md) — endpoint reference
- [`docs/calculations.md`](docs/calculations.md) — KPI/finance formulas
- [`docs/setup.md`](docs/setup.md) — detailed setup notes
- [`docs/protocol-configuration.md`](docs/protocol-configuration.md) — protocol categories & batch naming
- [`docs/deviations.md`](docs/deviations.md) — every place the implementation departs from or extends
  the original spec, with rationale, kept up to date as the authoritative log
