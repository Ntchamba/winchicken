#!/usr/bin/env bash
# Winchicken full regression suite — one command, re-runnable.
#
#   scripts/regression.sh            # everything: backend + frontend + live API + live UI
#   scripts/regression.sh --quick    # skip the long backend suite (fast inner-loop check)
#   scripts/regression.sh --no-ui    # skip the browser checks (no Chrome available)
#
# It proves, in one place, that the work of campaigns 1-6 and the FIX 1-7 queue still holds:
#   1. backend test suite  — unit + integration (the ORM-level proof of task completion, stock
#      deduction/undo, twice-daily time slots, shortfall, orphaned assignments, ...)
#   2. frontend test suite — component logic incl. batch-name validation and submission feedback
#   3. live API smoke      — the same FIX behaviours through the running deployed API (scripts/
#      regression_api.py): farm-local dates, multiple assignees, opening stock, complete/undo
#   4. live UI smoke       — the four recurring "fixed without fixing" items (sidebar scroll,
#      factory-reset button, batch-name validation, button alignment) + the shortfall panel,
#      observed in a real browser over CDP (scripts/regression_ui.mjs)
#
# Config (env, with sensible defaults for the winchicken-test stack):
#   REG_API_URL   default http://localhost:8010
#   REG_UI_URL    default http://localhost:5180
#   REG_COMPOSE   default the winchicken-test compose invocation below
#   Credentials:  REG_ADMIN_EMAIL/PASSWORD, REG_WORKER_EMAIL/PASSWORD (see regression_api.py)
#
# Exit code is 0 only if every section that ran passed.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REG_API_URL="${REG_API_URL:-http://localhost:8010}"
REG_UI_URL="${REG_UI_URL:-http://localhost:5180}"
REG_COMPOSE="${REG_COMPOSE:-docker compose -p winchicken-test -f docker-compose.yml -f docker-compose.test.yml}"
export REG_API_URL REG_UI_URL

QUICK=0; NO_UI=0
for arg in "$@"; do
  case "$arg" in
    --quick) QUICK=1 ;;
    --no-ui) NO_UI=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

declare -a SUMMARY
fail_count=0
section() { echo; echo "════════════════════════════════════════════════════════════"; echo "▶ $1"; echo "════════════════════════════════════════════════════════════"; }
record() { # name, exit_code
  if [ "$2" -eq 0 ]; then SUMMARY+=("PASS  $1"); else SUMMARY+=("FAIL  $1"); fail_count=$((fail_count + 1)); fi
}

cd "$ROOT"

# 1. Backend -----------------------------------------------------------------------------------
if [ "$QUICK" -eq 0 ]; then
  section "Backend test suite (Django, unit + integration)"
  $REG_COMPOSE exec -T web python manage.py test --noinput
  record "backend tests" $?
else
  SUMMARY+=("SKIP  backend tests (--quick)")
fi

# 2. Frontend ----------------------------------------------------------------------------------
section "Frontend test suite (vitest)"
if command -v npm >/dev/null 2>&1; then
  ( cd "$ROOT/frontend" && npm run test )   # package.json "test" is already `vitest run`
  record "frontend tests" $?
else
  SUMMARY+=("SKIP  frontend tests (npm not found)")
fi

# 3. Live API smoke ----------------------------------------------------------------------------
section "Live API regression (FIX 1-7) against $REG_API_URL"
python3 "$ROOT/scripts/regression_api.py"
record "live API smoke" $?
# The opening-stock check's item has no API delete; remove it (and its movements) here.
$REG_COMPOSE exec -T web python manage.py shell --no-imports -c \
  "from apps.stock.models import StockItem; StockItem.objects.filter(name='REG-Article-Temporaire').delete()" \
  2>/dev/null || echo "  (could not remove REG-Article-Temporaire — compose stack not reachable)"

# 4. Live UI smoke -------------------------------------------------------------------------------
if [ "$NO_UI" -eq 0 ]; then
  section "Live UI regression (recurring-four + shortfall) against $REG_UI_URL"
  CHROME="$(command -v google-chrome || command -v chromium || command -v chromium-browser || true)"
  if [ -z "$CHROME" ]; then
    echo "No Chrome/Chromium found — skipping the browser checks (run with --no-ui to silence)."
    SUMMARY+=("SKIP  live UI smoke (no Chrome)")
  elif ! command -v node >/dev/null 2>&1; then
    echo "node not found — skipping the browser checks."
    SUMMARY+=("SKIP  live UI smoke (no node)")
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
      echo "Chrome did not expose a debug endpoint — skipping UI checks."
      SUMMARY+=("SKIP  live UI smoke (Chrome debug port)")
    else
      node "$ROOT/scripts/regression_ui.mjs" "$WS" "$REG_UI_URL" "$REG_API_URL"
      record "live UI smoke" $?
    fi
    kill "$CHROME_PID" 2>/dev/null
    wait "$CHROME_PID" 2>/dev/null
    rm -rf "$PROFILE" 2>/dev/null
  fi
else
  SUMMARY+=("SKIP  live UI smoke (--no-ui)")
fi

# Summary --------------------------------------------------------------------------------------
echo; echo "════════════════════════════════════════════════════════════"
echo "  REGRESSION SUMMARY"
echo "════════════════════════════════════════════════════════════"
for line in "${SUMMARY[@]}"; do echo "  $line"; done
echo "════════════════════════════════════════════════════════════"
if [ "$fail_count" -eq 0 ]; then
  echo "  ✅ ALL GREEN"
  exit 0
else
  echo "  ❌ $fail_count section(s) FAILED"
  exit 1
fi
