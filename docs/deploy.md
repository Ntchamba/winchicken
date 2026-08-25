# Deploying (Vercel + Railway)

Frontend on Vercel, backend (API + Celery worker + Postgres + Redis) on Railway.
Both are click-through from their dashboards — no CLI needed, and none of this
repo's local Docker Compose setup changes.

## Backend — Railway

1. **New Project → Deploy from GitHub repo** → select `ntchamba/winchicken`.
2. Railway creates one service from the repo root; open its **Settings**:
   - **Root Directory**: `backend`
   - Build/start are already picked up from `backend/railway.toml` (Dockerfile
     build, `gunicorn` start command, healthcheck on `/api/health/`).
   - Rename this service to `web`.
3. **+ New → Database → Add PostgreSQL** (in the same project).
4. **+ New → Database → Add Redis** (in the same project).
5. **+ New → Empty Service** from the same GitHub repo, **Root Directory**:
   `backend` again. Rename it `worker`. In its Settings → Deploy, set
   **Custom Start Command**: `celery -A config worker -l info` (overrides the
   `railway.toml` gunicorn command for this service only).
6. On **both** `web` and `worker`, set these variables (Settings → Variables).
   Reference the Postgres/Redis plugins by name so credentials stay in sync
   automatically — replace `Postgres`/`Redis` below with whatever you named
   those two plugins if different:

   ```
   SECRET_KEY=<generate a random 50-char string>
   DEBUG=False
   ALLOWED_HOSTS=.up.railway.app,<your Railway domain once assigned>
   DB_NAME=${{Postgres.PGDATABASE}}
   DB_USER=${{Postgres.PGUSER}}
   DB_PASSWORD=${{Postgres.PGPASSWORD}}
   DB_HOST=${{Postgres.PGHOST}}
   DB_PORT=${{Postgres.PGPORT}}
   REDIS_URL=${{Redis.REDIS_URL}}
   CORS_ALLOWED_ORIGINS=https://<your-vercel-project>.vercel.app
   SMS_PROVIDER=console
   ```

   `SMS_PROVIDER=console` logs SMS instead of sending — swap in a real
   provider's `SMS_PROVIDER`/`SMS_PROVIDER_API_KEY` later, same as local dev
   (see root `README.md`).
7. On `web`, Settings → Networking → **Generate Domain**. Copy that URL — it's
   the API base for the frontend step below.
8. Once both services show healthy, run the first migration/admin setup from
   Railway's shell (Settings → the `web` service → three-dot menu →
   **Shell**, or `railway run` locally if you have the CLI):
   ```bash
   python manage.py createsuperuser   # optional, /admin/ only
   ```
   (`migrate` already runs on every deploy via the `railway.toml` start
   command — no separate step needed.)

## Frontend — Vercel

1. **Add New → Project → Import Git Repository** → `ntchamba/winchicken`.
2. In the import screen: **Root Directory** → `frontend`. Framework preset
   (Vite) is auto-detected; build command `npm run build`, output `dist`
   (defaults, no change needed). `frontend/vercel.json` (SPA rewrite, so
   client-side routes like `/dashboard` don't 404 on refresh) is already
   picked up automatically.
3. **Environment Variables** → add:
   ```
   VITE_API_URL=https://<railway-web-domain-from-step-7-above>/api
   ```
4. **Deploy.**

## After both are live

- Open the Vercel URL → **"Créer la ferme"** to seed the first account (no
  demo data/credentials are seeded — same as local, see root `README.md`).
- If `CORS_ALLOWED_ORIGINS` on Railway was set before the Vercel domain was
  known, update it to the real `https://....vercel.app` URL and redeploy the
  `web` service (Railway → Deployments → Redeploy) — a mismatch here shows up
  as the browser blocking API calls with a CORS error, not a 4xx from Django.
