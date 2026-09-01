#!/usr/bin/env bash
# post-edit-verify.sh — PostToolUse verification gate for frontend edits.
#
# WHY: this project has a documented history (docs/deviations.md) of changes reported as
# working that weren't. This hook runs the real frontend build + lint (and the one test file
# related to the edited component, if there is one) immediately after every .css / .jsx / .tsx
# edit, so a build/lint/test regression surfaces at the moment it is introduced instead of at
# the end of a task — or never.
#
# HOW IT BLOCKS: PostToolUse runs *after* the edit is written, so it cannot un-write the file.
# On failure it exits 2, which Claude Code treats as a blocking error: the stderr below is fed
# back to the model, so the edit cannot be silently considered complete — the failure must be
# addressed before moving on.
#
# SCOPE / CHOICES:
#   * Only frontend .css / .jsx / .tsx files trigger it (other edits exit 0 immediately).
#   * `npm run build` + `npm run lint` are the HARD gate (fast, deterministic here: ~5s total).
#   * Tests: only the single test file related to the edited component is run, never the full
#     suite (a keystroke-level full-suite run is both discouraged by design and, in this repo's
#     current environment, unreliable — vitest frequently hangs when handed multiple files).
#     A related test that fails is a hard gate; no related test, or a test run that exceeds the
#     timeout, is reported but does NOT block.
#
# DISABLE: `/hooks` (interactive) to toggle, or `"disableAllHooks": true` in settings.json.

set -uo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
FRONTEND_DIR="$PROJECT_DIR/frontend"

# --- read the edited file path from the hook's stdin JSON ---------------------
payload="$(cat)"
file_path="$(printf '%s' "$payload" | jq -r '.tool_input.file_path // .tool_response.filePath // empty' 2>/dev/null)"

# Nothing to check: not a frontend css/jsx/tsx edit.
case "$file_path" in
  "$FRONTEND_DIR"/*.css|"$FRONTEND_DIR"/*.jsx|"$FRONTEND_DIR"/*.tsx) ;;
  */frontend/*.css|*/frontend/*.jsx|*/frontend/*.tsx) ;;
  *) exit 0 ;;
esac

[ -d "$FRONTEND_DIR" ] || exit 0
cd "$FRONTEND_DIR" || exit 0

fail() { printf '\n[post-edit-verify] BLOCKED — %s\n%s\n' "$1" "$2" >&2; exit 2; }

# --- 1. build (hard gate) ---------------------------------------------------
build_out="$(npm run build 2>&1)" || fail "frontend build failed after editing $file_path" "$build_out"

# --- 2. lint (hard gate) --------------------------------------------------
lint_out="$(npm run lint 2>&1)" || fail "lint (oxlint) failed after editing $file_path" "$lint_out"

# --- 3. related test file only (best-effort, not a hard gate on timeout) ----
base="$(basename "$file_path")"
name="${base%.*}"
dir="$(dirname "$file_path")"
test_file=""
for cand in \
  "$dir/__tests__/$name.test.jsx" \
  "$dir/__tests__/$name.test.tsx" \
  "$dir/$name.test.jsx" \
  "$dir/$name.test.tsx"; do
  [ -f "$cand" ] && { test_file="$cand"; break; }
done

test_note="no related test file found for $name — skipped"
if [ -n "$test_file" ]; then
  rel="${test_file#"$FRONTEND_DIR"/}"
  if test_out="$(timeout 90 npx vitest run "$rel" 2>&1)"; then
    test_note="related test passed: $rel"
  else
    rc=$?
    if [ "$rc" -eq 124 ]; then
      test_note="related test ($rel) exceeded 90s and was skipped (not treated as a failure — see hook README)"
    else
      fail "related test failed after editing $file_path" "$test_out"
    fi
  fi
fi

printf '[post-edit-verify] OK — build + lint passed for %s | %s\n' "$file_path" "$test_note"
exit 0
