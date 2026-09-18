# Responsive audit

Drives the real app in a real headless Chrome at 375 / 768 / 1440 and measures what a phone user
actually hits. It reads the app; it never changes it.

```bash
cd frontend
npm run audit:responsive                                  # every view, every width, screenshots
npm run audit:responsive -- --widths=375 --views=cashier  # one view, one width
npm run audit:responsive -- --role=worker --no-shots      # worker side only, measurements only
```

Results land in `out/` (gitignored): `audit-<width>.json` per width, `audit.json` for the whole
run, and `out/shots/<width>-<role>-<view>.png`.

## What it measures

| field | meaning |
|---|---|
| `pageOverflow` | `documentElement.scrollWidth - innerWidth` — the page scrolls sideways |
| `widerBoxes` | boxes laid out wider than the viewport, i.e. what causes the overflow |
| `clipped` | `overflow-x: hidden/clip` **and** content wider than the box — content no one can reach |
| `hiddenScroll` | scrollable but with no affordance — reachable only by guessing to swipe |
| `smallTargets` | tappable elements under 44px in either dimension |
| `hiddenColumns` | `<th>/<td>` collapsed to zero width — a column deleted from the user |
| `nav` | is the drawer toggle rendered, displayed and sized; where the sidebar sits |

`clipped` and `hiddenColumns` are the ones that lose information rather than look bad.

## Requirements

Chrome (`google-chrome-stable`, override with `CHROME_BIN`) and a running stack. No npm
dependency: the driver in `cdp.mjs` speaks CDP over Node 24's global `WebSocket`, deliberately,
so a farm laptop never has to install a browser-automation package.

Defaults point at the isolated test stack — UI `:5180`, API `:8010`, logins
`admin@test.local` / `ouvrier01@test.local`. Override with `--base` / `--api` or
`BASE_URL` / `API_URL` / `AUDIT_ADMIN` / `AUDIT_ADMIN_PW` / `AUDIT_WORKER` / `AUDIT_WORKER_PW`.

```bash
docker compose -p winchicken-test -f docker-compose.yml -f docker-compose.test.yml up -d
```

Chrome runs with `TZ=Africa/Douala`, so anything date-defaulting behaves as it does on the farm.

## Reading a run

A line is flagged with `!` when the page overflows, clips content, or hides a column. Tap-target
counts are advisory — the sidebar search input and the notification bell account for most of them
on every view, so compare the number against the same view before the change rather than to zero.
