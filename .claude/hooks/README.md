# `.claude/hooks/`

## `post-edit-verify.sh` — PostToolUse verification gate

### Why it exists

This project has a documented history (`docs/deviations.md`) of changes reported as working
that weren't. This hook runs the **real frontend build + lint** — and the one test file
related to the edited component, if one exists — immediately after every `.css` / `.jsx` /
`.tsx` edit under `frontend/`. A build/lint/test regression then surfaces at the moment it is
introduced instead of at the end of a task, or never.

### How it is wired

`.claude/settings.json`:

```json
"hooks": {
  "PostToolUse": [
    { "matcher": "Edit|Write|MultiEdit",
      "hooks": [ { "type": "command",
                   "command": "\"${CLAUDE_PROJECT_DIR}/.claude/hooks/post-edit-verify.sh\"",
                   "timeout": 180 } ] }
  ]
}
```

The hook receives the tool-call JSON on stdin and reads `.tool_input.file_path`.

### What it does

| Step | Tool | Gate |
|------|------|------|
| 1 | `npm run build` (`vite build`) | **hard** — non-zero → hook exits 2 |
| 2 | `npm run lint` (`oxlint`) | **hard** — any `error:` (oxlint exit 1) → hook exits 2 |
| 3 | `npx vitest run <related test file>` | **soft** — a failing related test → exit 2; **no** related test, or a run that exceeds 90 s → reported, not blocked |

Non-`frontend` files, and non-`.css/.jsx/.tsx` files, exit 0 immediately.

### How "blocking" actually works

`PostToolUse` runs **after** the edit is written to disk — it cannot un-write the file. On
failure it **exits 2**, which Claude Code treats as a *blocking error*: the hook's stderr is
fed back to the model, so the edit cannot be silently treated as complete — the failure has to
be fixed before moving on.

### Choices made (per the task's "note your choice")

- **Only the related test file is ever run, never the full suite.** A keystroke-level full-suite
  run is both discouraged by design and, in this repo's current environment, unreliable —
  `vitest` frequently hangs when handed multiple files. The related file is found by looking for
  `__tests__/<Name>.test.jsx|tsx` or `<name>.test.jsx|tsx` next to the edited file.
- **A test run that exceeds 90 s is treated as "skipped", not "failed"**, so a flaky/hanging
  `vitest` invocation can't wedge every edit. Build + lint remain the reliable hard gate.

### Known limitation — CSS syntax errors

`vite build` only processes CSS that is actually imported into the app and is lenient about
malformed rules; `oxlint` does not lint CSS at all (no Stylelint is configured in this project).
So an **isolated CSS syntax error is not reliably caught** by steps 1–2. A CSS error bad enough
to break an *imported* stylesheet's build will fail step 1. To catch CSS syntax errors
specifically, add `stylelint` to `frontend/` and a `stylelint "src/**/*.css"` step to this hook.

### Disabling

- `/hooks` (interactive) to toggle it off for a session.
- `"disableAllHooks": true` in `.claude/settings.json` (disables *all* hooks).

### Note on activation

Claude Code's settings watcher only watches directories that already had a settings file when
the session started. If `.claude/settings.json` was **created** during a running session, open
`/hooks` once (reloads config) or restart the session for this hook to take effect.
