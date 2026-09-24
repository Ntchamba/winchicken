#!/bin/sh
# Production web process (docker-compose.prod.yml `web`). Migrations run on every start, so an
# update is "new image + restart" with nothing to type; the launcher takes a backup first.
set -e
python manage.py migrate --noinput
python manage.py collectstatic --noinput --verbosity 0
# 2 workers x 4 threads: enough for one farm (a PC plus a few phones) inside the 4 GB budget.
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-2}" \
    --threads "${GUNICORN_THREADS:-4}" \
    --timeout 120 \
    --max-requests 1000 --max-requests-jitter 100 \
    --access-logfile -
