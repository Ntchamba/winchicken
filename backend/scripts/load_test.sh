#!/usr/bin/env bash
# Load test: (re)create a throwaway *_load database on the isolated test stack's Postgres,
# seed it with seed_load_farm, then time every screen with bench_load.
#
#   backend/scripts/load_test.sh                        # 1M birds, 20k employees (defaults)
#   LOAD_DB=winchicken_small_load backend/scripts/load_test.sh --birds 5000 --houses 4 \
#       --employees 40 --stock-items 40 --sales-per-day 10 --expenses-per-day 5 --orders-per-day 2
#   SKIP_SEED=1 BENCH_ARGS="--json /app/logs/after.json" backend/scripts/load_test.sh
#
# Arguments are passed to seed_load_farm. It never touches `winchicken` (dev) or `winchicken_test`:
# the name must end in `_load`, and both management commands refuse anything else on their own.
# Runs in a one-off `web` container with SMS on the console provider, Web Push off and no Redis
# broker, so the stack's live Twilio / VAPID credentials cannot be used and nothing reaches the
# test stack's worker.
set -euo pipefail
cd "$(dirname "$0")/../.."

LOAD_DB="${LOAD_DB:-winchicken_load}"
case "$LOAD_DB" in *_load) ;; *) echo "LOAD_DB must end in _load (got $LOAD_DB)" >&2; exit 1 ;; esac

COMPOSE=(docker compose -p winchicken-test -f docker-compose.yml -f docker-compose.test.yml)
RUN=("${COMPOSE[@]}" run --rm --no-deps -T
  -e DB_NAME="$LOAD_DB" -e SMS_PROVIDER=console -e WEB_PUSH_ENABLED=False
  -e TWILIO_ACCOUNT_SID= -e TWILIO_AUTH_TOKEN= -e VAPID_PRIVATE_KEY= -e REDIS_URL=memory://
  web)

if [ -z "${SKIP_SEED:-}" ]; then
  "${COMPOSE[@]}" exec -T db psql -U winchicken -d postgres -v ON_ERROR_STOP=1 \
    -c "DROP DATABASE IF EXISTS $LOAD_DB WITH (FORCE)" -c "CREATE DATABASE $LOAD_DB"
  "${RUN[@]}" python manage.py migrate --no-input -v 0
  "${RUN[@]}" python manage.py seed_load_farm "$@"
  "${COMPOSE[@]}" exec -T db psql -U winchicken -d "$LOAD_DB" -c "VACUUM ANALYZE" >/dev/null
fi
# shellcheck disable=SC2086
"${RUN[@]}" python manage.py bench_load ${BENCH_ARGS:-}
