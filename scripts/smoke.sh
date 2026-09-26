#!/usr/bin/env bash
# Winchicken pre-deployment smoke test — the critical path only, in well under 2 minutes.
#
#   scripts/smoke.sh            # API critical path + browser (login form, dashboard renders)
#   scripts/smoke.sh --no-ui    # API only (no Chrome on this machine)
#
# Run it before every deployment. It checks, in order, and stops at the first broken link:
#   app boots -> login works -> dashboard loads -> a batch is visible -> a task can be completed
#   -> stock moves -> a sale records                               (scripts/smoke_api.py)
#   SPA boots -> the real login form logs in -> the dashboard renders an active batch with no JS
#   exception or failed API call                                    (scripts/smoke_ui.mjs)
#
# The API half builds its own throwaway fixture named SMOKE-<epoch> (house, batch, stock item,
# protocol line) and removes it afterwards, so it neither depends on nor pollutes the farm's data.
# The sale and stock item it creates have no API delete; they are removed here through manage.py.
# The browser half needs at least one ACTIVE batch on the farm (it looks for its name).
#
# The full suite (backend + frontend tests + FIX 1-7 + recurring UI items) is scripts/regression.sh.
#
# Config (env, defaults = the winchicken-test stack):
#   SMOKE_API_URL  default http://localhost:8010
#   SMOKE_UI_URL   default http://localhost:5180
#   SMOKE_COMPOSE  default the winchicken-test compose invocation; set to "" to skip DB cleanup
#   SMOKE_ADMIN_EMAIL / SMOKE_ADMIN_PASSWORD  an ADMIN or FARM_MANAGER account on that farm
#
# Exit code 0 only if every step passed.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export SMOKE_API_URL="${SMOKE_API_URL:-http://localhost:8010}"
export SMOKE_UI_URL="${SMOKE_UI_URL:-http://localhost:5180}"
SMOKE_COMPOSE="${SMOKE_COMPOSE-docker compose -p winchicken-test -f docker-compose.yml -f docker-compose.test.yml}"
export SMOKE_RUN_ID="SMOKE-$(date +%s)"

NO_UI=0
for arg in "$@"; do
  case "$arg" in
    --no-ui) NO_UI=1 ;;
    -h|--help) sed -n '2,27p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

START=$(date +%s)
cd "$ROOT"
api_rc=0; ui_rc=0

python3 "$ROOT/scripts/smoke_api.py"
api_rc=$?

# Remove what the API cannot: the sale and the stock item (its movements cascade with it).
if [ -n "$SMOKE_COMPOSE" ]; then
  $SMOKE_COMPOSE exec -T web python manage.py shell --no-imports -c "
from apps.finance.models import Sale
from apps.stock.models import StockItem
s = Sale.objects.filter(customer='$SMOKE_RUN_ID').delete()[0]
i = StockItem.objects.filter(name='$SMOKE_RUN_ID').delete()[0]
print(f'  cleanup: {s} sale row(s), {i} stock row(s) incl. movements removed')
" 2>/dev/null || echo "  cleanup skipped: compose stack not reachable — remove sale/stock item named $SMOKE_RUN_ID by hand"
else
  echo "  cleanup skipped (SMOKE_COMPOSE empty) — remove any sale/stock item named $SMOKE_RUN_ID by hand"
fi

if [ "$NO_UI" -eq 0 ] && [ "$api_rc" -eq 0 ]; then
  CHROME="$(command -v google-chrome || command -v chromium || command -v chromium-browser || true)"
  if [ -z "$CHROME" ] || ! command -v node >/dev/null 2>&1; then
    echo "No Chrome/Chromium or node — browser half skipped (use --no-ui to silence)."
  else
    PORT=$(( (RANDOM % 2000) + 9300 ))
    PROFILE="$(mktemp -d)"
    setsid "$CHROME" --headless=new --no-sandbox --disable-gpu --no-first-run \
      --remote-debugging-port="$PORT" --user-data-dir="$PROFILE" about:blank >/dev/null 2>&1 &
    CHROME_PID=$!
    WS=""
    for _ in $(seq 20); do
      sleep 0.5
      WS="$(curl -s "http://localhost:$PORT/json/version" 2>/dev/null | python3 -c 'import json,sys;print(json.load(sys.stdin)["webSocketDebuggerUrl"])' 2>/dev/null || true)"
      [ -n "$WS" ] && break
    done
    if [ -z "$WS" ]; then
      echo "Chrome did not expose a debug endpoint — browser half FAILED to start."; ui_rc=1
    else
      node "$ROOT/scripts/smoke_ui.mjs" "$WS" "$SMOKE_UI_URL" "$SMOKE_API_URL"
      ui_rc=$?
    fi
    kill "$CHROME_PID" 2>/dev/null; wait "$CHROME_PID" 2>/dev/null; rm -rf "$PROFILE" 2>/dev/null
  fi
fi

ELAPSED=$(( $(date +%s) - START ))
if [ "$api_rc" -eq 0 ] && [ "$ui_rc" -eq 0 ]; then
  echo "✅ SMOKE PASSED in ${ELAPSED}s"; exit 0
else
  echo "❌ SMOKE FAILED in ${ELAPSED}s — do not deploy"; exit 1
fi
