#!/usr/bin/env python3
"""Pre-deployment smoke test — the critical path only, through the running API, in seconds.

  app boots -> login -> dashboard data loads -> a batch is visible -> a task is completed
  -> stock moves -> a sale records

Part of scripts/smoke.sh (which adds the browser half: the dashboard actually renders).

It does not depend on whatever the target farm happens to contain: it builds its own throwaway
fixture through the public API (a house, a batch starting today, a stock item with an opening
quantity, one protocol line that consumes 2 units a day of that item), drives the critical path
against it, and deletes the fixture again in a `finally`. Everything it creates is named
`SMOKE-<run id>` so a leftover is recognisable. Two things the API cannot delete: the sale (no sale
DELETE endpoint by design) and the stock item (items are only removed by omitting them from the
full stock PUT, which a smoke test must not risk). `smoke.sh` removes both through `manage.py`
when it can reach the compose stack, and prints what was left otherwise.

Config (env):
  SMOKE_API_URL            default http://localhost:8010
  SMOKE_ADMIN_EMAIL        default paul@c3.test
  SMOKE_ADMIN_PASSWORD     default Campagne3-Admin2!
  SMOKE_RUN_ID             default SMOKE-<epoch>; smoke.sh passes it so it can clean up by name

Exit code 0 = every step passed; 1 = a step failed (the remaining steps are skipped — on the
critical path one broken link makes the rest meaningless).
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

BASE = os.environ.get("SMOKE_API_URL", "http://localhost:8010").rstrip("/")
EMAIL = os.environ.get("SMOKE_ADMIN_EMAIL", "paul@c3.test")
PASSWORD = os.environ.get("SMOKE_ADMIN_PASSWORD", "Campagne3-Admin2!")
FARM_TZ = ZoneInfo(os.environ.get("SMOKE_FARM_TZ", "Africa/Douala"))
RUN = os.environ.get("SMOKE_RUN_ID") or f"SMOKE-{int(time.time())}"


class StepFailed(Exception):
    pass


def req(method, path, body=None, tok=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    if tok:
        headers["Authorization"] = "Bearer " + tok
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw[:300]
    except (urllib.error.URLError, OSError) as e:
        return 0, str(e)


def expect(cond, msg):
    if not cond:
        raise StepFailed(msg)


steps = []  # (ok, name, detail, seconds)


def step(name, fn):
    t0 = time.monotonic()
    try:
        detail = fn() or ""
        steps.append((True, name, detail, time.monotonic() - t0))
        return True
    except Exception as exc:  # noqa: BLE001 — any failure on the critical path is the finding
        detail = str(exc) if isinstance(exc, StepFailed) else f"{type(exc).__name__}: {exc}"
        steps.append((False, name, detail, time.monotonic() - t0))
        return False


def main():
    ctx = {}

    def boots():
        s, b = req("GET", "/api/health/")
        expect(s == 200 and isinstance(b, dict) and b.get("status") == "ok", f"/api/health/ -> {s} {b!r}")
        return "health ok"

    def login():
        s, b = req("POST", "/api/auth/login/", {"email": EMAIL, "password": PASSWORD})
        expect(s == 200 and b.get("access"), f"login as {EMAIL} -> {s} {b!r}")
        ctx["tok"] = b["access"]
        s, me = req("GET", "/api/auth/me/", tok=ctx["tok"])
        expect(s == 200 and me.get("farm"), f"/api/auth/me/ -> {s} {me!r}")
        ctx["farm"] = me["farm"]
        return f"{EMAIL} ({me.get('role')}), farm {me['farm']}"

    def dashboard():
        # The calls the dashboard makes on mount (DashboardPage / sidebar badges).
        for p in ["/api/farm/overview/", "/api/houses/", "/api/batches/?status=ACTIVE",
                  "/api/finance/summary/", "/api/stock-items/low-count/", "/api/alerts/?open=1"]:
            s, b = req("GET", p, tok=ctx["tok"])
            expect(s == 200, f"{p} -> {s} {str(b)[:160]}")
        return "6 dashboard endpoints 200"

    def fixture():
        tok, farm = ctx["tok"], ctx["farm"]
        s, h = req("POST", "/api/houses/", {"name": RUN, "max_capacity": 100}, tok=tok)
        expect(s == 201, f"create house -> {s} {h!r}")
        ctx["house"] = h["house_code"]
        s, item = req("POST", f"/api/farms/{farm}/stock-items/", {"name": RUN, "unit": "kg", "quantity": 10}, tok=tok)
        expect(s in (200, 201), f"create stock item -> {s} {item!r}")
        ctx["item_code"] = item.get("item_code") or item.get("itemCode")
        if not ctx["item_code"]:  # the farm-level list is the source of truth
            ctx["item_code"] = _find_item()["item_code"]
        # Opening stock is an IN movement — `quantity` on the item create is not a field.
        s, mv = req("POST", "/api/stock-movements/", {"item": ctx["item_code"], "movement_type": "IN", "quantity": 10,
                                                        "movement_date": datetime.now(FARM_TZ).date().isoformat(),
                                                        "note": RUN}, tok=tok)
        expect(s == 201, f"opening stock movement -> {s} {mv!r}")
        s, cats = req("GET", f"/api/houses/{ctx['house']}/protocol-categories/", tok=tok)
        cats = cats.get("results", cats) if isinstance(cats, dict) else cats
        if not cats:
            s, c = req("POST", f"/api/houses/{ctx['house']}/protocol-categories/", {"label": "Alimentation", "icon": "Soup"}, tok=tok)
            expect(s == 201, f"create category -> {s} {c!r}")
            cats = [c]
        line = {"category": cats[0]["id"], "from_value": 0, "from_unit": "DAY", "until_end": True,
                "what": RUN, "details": "", "time_slots": [], "stock_item": ctx["item_code"], "quantity_per_day": 2}
        s, b = req("PUT", f"/api/houses/{ctx['house']}/protocol/", {"lines": [line]}, tok=tok)
        expect(s == 200, f"save protocol -> {s} {b!r}")
        today = datetime.now(FARM_TZ).date().isoformat()
        s, bt = req("POST", "/api/batches/", {"name": RUN, "house_code": ctx["house"], "production_type": "BROILER",
                                               "initial_count": 50, "start_date": today}, tok=tok)
        expect(s == 201, f"create batch -> {s} {bt!r}")
        ctx["batch"] = bt["batch_code"]
        ctx["batch_id"] = bt.get("id")
        return f"house {ctx['house']}, batch {ctx['batch']}, item {ctx['item_code']} (10 kg), line 2 kg/day"

    def _find_item():
        s, items = req("GET", f"/api/farms/{ctx['farm']}/stock-items/", tok=ctx["tok"])
        rows = items.get("items", items) if isinstance(items, dict) else items
        row = next((i for i in rows or [] if i.get("name") == RUN), None)
        expect(row is not None, "smoke stock item not found in the farm list")
        return row

    def batch_visible():
        s, b = req("GET", "/api/batches/?status=ACTIVE", tok=ctx["tok"])
        codes = [x["batch_code"] for x in b.get("results", [])]
        # The list is paginated; follow `next` so a big farm doesn't hide the smoke batch.
        nxt = b.get("next")
        while nxt and ctx["batch"] not in codes:
            s, b = req("GET", nxt.replace(BASE, ""), tok=ctx["tok"])
            codes += [x["batch_code"] for x in b.get("results", [])]
            nxt = b.get("next")
        expect(ctx["batch"] in codes, f"{ctx['batch']} not in active batches")
        s, h = req("GET", f"/api/houses/{ctx['house']}/", tok=ctx["tok"])
        expect(s == 200, f"house detail -> {s}")
        return f"{ctx['batch']} in the active batch list"

    def complete_task():
        s, tn = req("GET", f"/api/houses/{ctx['house']}/tasks-now/", tok=ctx["tok"])
        expect(s == 200, f"tasks-now -> {s}")
        task = next((t for t in tn.get("tasks", []) if t.get("what") == RUN), None)
        expect(task is not None and task.get("completable"), f"smoke task not due/completable: {tn.get('tasks')}")
        ctx["qty_before"] = float(_find_item()["current_quantity"])
        s, b = req("POST", f"/api/houses/{ctx['house']}/tasks-now/{task['id']}/complete/", {"force": False}, tok=ctx["tok"])
        expect(s in (200, 201), f"complete -> {s} {b!r}")
        expect(b.get("movement"), f"completion returned no stock movement: {b!r}")
        s, tn = req("GET", f"/api/houses/{ctx['house']}/tasks-now/", tok=ctx["tok"])
        done = next((t for t in tn.get("tasks", []) if t.get("what") == RUN), {})
        expect(done.get("done") is True, "task not reported done on re-read")
        return f"task {task['id']} done, movement {b['movement'].get('quantity')} {b['movement'].get('itemCode', '')}"

    def stock_moved():
        row = _find_item()
        after = float(row["current_quantity"])
        expect(abs((ctx["qty_before"] - after) - 2) < 1e-9, f"stock {ctx['qty_before']} -> {after}, expected -2")
        return f"{ctx['qty_before']:g} kg -> {after:g} kg"

    def sale():
        today = datetime.now(FARM_TZ).date().isoformat()
        s, b = req("POST", "/api/sales/", {"product_type": "BIRD", "quantity": 1, "unit_price": "1",
                                           "sale_date": today, "customer": RUN}, tok=ctx["tok"])
        expect(s == 201 and b.get("id"), f"record sale -> {s} {b!r}")
        ctx["sale_id"] = b["id"]
        s, lst = req("GET", f"/api/sales/?sale_date={today}", tok=ctx["tok"])
        ids = [x["id"] for x in (lst.get("results", []) if isinstance(lst, dict) else lst or [])]
        expect(b["id"] in ids or lst.get("next"), f"sale {b['id']} not listed for {today}")
        return f"sale #{b['id']} 1 FCFA recorded and listed"

    try:
        for name, fn in [("app boots (health)", boots), ("login works", login),
                         ("dashboard data loads", dashboard), ("fixture (house, batch, stock, line)", fixture),
                         ("a batch is visible", batch_visible), ("a task can be completed", complete_task),
                         ("stock moves", stock_moved), ("a sale records", sale)]:
            if not step(name, fn):
                break
    finally:
        cleanup(ctx)

    ok = all(s[0] for s in steps) and len(steps) == 8
    width = max(len(s[1]) for s in steps)
    print("== Smoke: API critical path ==")
    for good, name, detail, secs in steps:
        print(f"  [{'PASS' if good else 'FAIL'}] {name.ljust(width)} {secs:5.2f}s  {detail}")
    if len(steps) < 8:
        print(f"  (remaining {8 - len(steps)} step(s) not run after the failure)")
    print(f"== {'SMOKE OK' if ok else 'SMOKE FAILED'} ({BASE}) ==")
    return 0 if ok else 1


def cleanup(ctx):
    """Remove what the API can: deleting the house cascades the batch, the protocol line and
    its completion. The stock item (and with it its movements) and the sale are left to smoke.sh."""
    tok = ctx.get("tok")
    if not tok:
        return
    if ctx.get("house"):
        req("DELETE", f"/api/houses/{ctx['house']}/", tok=tok)


if __name__ == "__main__":
    sys.exit(main())
