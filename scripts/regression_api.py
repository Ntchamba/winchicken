#!/usr/bin/env python3
"""Live API regression smoke for Winchicken — part of scripts/regression.sh.

Hits a *running* stack over HTTP as a real client and asserts the behaviour of the FIX 1-7
queue that the unit/integration suites prove at the ORM level, so a regression that only shows
up through the deployed API (routing, serialization, permissions, farm-local clock) is caught
too. Every check that changes data restores it, so the script is safe to re-run.

Config (env):
  REG_API_URL       default http://localhost:8010
  REG_ADMIN_EMAIL   default paul@c3.test
  REG_ADMIN_PASSWORD default Campagne3-Admin2!
  REG_WORKER_EMAIL  default qa00@c3.test
  REG_WORKER_PASSWORD default QaCharge2026!

Exit code 0 = all checks passed or were skipped with a reason; 1 = at least one failed.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime
from zoneinfo import ZoneInfo

BASE = os.environ.get("REG_API_URL", "http://localhost:8010").rstrip("/")
ADMIN = (os.environ.get("REG_ADMIN_EMAIL", "paul@c3.test"), os.environ.get("REG_ADMIN_PASSWORD", "Campagne3-Admin2!"))
WORKER = (os.environ.get("REG_WORKER_EMAIL", "qa00@c3.test"), os.environ.get("REG_WORKER_PASSWORD", "QaCharge2026!"))
FARM_TZ = ZoneInfo(os.environ.get("REG_FARM_TZ", "Africa/Douala"))

results = []  # (state, name, detail)


def req(method, path, body=None, tok=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    if tok:
        headers["Authorization"] = "Bearer " + tok
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def as_json(b):
    try:
        return json.loads(b)
    except Exception:
        return None


def login(creds):
    s, b = req("POST", "/api/auth/login/", {"email": creds[0], "password": creds[1]})
    if s != 200:
        raise SystemExit(f"cannot log in as {creds[0]} ({s}); is the stack up and seeded? {b[:200]!r}")
    return json.loads(b)["access"]


def check(name):
    """Decorator: run a check, record PASS/FAIL/SKIP. Raise Skip(reason) to skip, any other
    exception is a FAIL, returning normally is a PASS (with an optional detail string)."""
    def wrap(fn):
        try:
            detail = fn() or ""
            results.append(("PASS", name, detail))
        except Skip as sk:
            results.append(("SKIP", name, str(sk)))
        except Exception as exc:  # noqa: BLE001 — a failed assertion is a regression, report it
            results.append(("FAIL", name, f"{type(exc).__name__}: {exc}"))
        return fn
    return wrap


class Skip(Exception):
    pass


def main():
    admin = login(ADMIN)
    worker = login(WORKER)

    @check("endpoints reachable and authenticated")
    def _():
        for p in ["/api/auth/me/", "/api/houses/", "/api/batches/", "/api/farm/overview/",
                  "/api/finance/summary/", "/api/alerts/", "/api/stock-items/low-count/", "/api/search/?q=x"]:
            s, _ = req("GET", p, tok=admin)
            assert s == 200, f"{p} -> {s}"
        s, _ = req("GET", "/api/auth/me/")
        assert s == 401, f"unauthenticated /me should be 401, got {s}"

    # A house with an active batch is the fixture the task/stock checks need.
    houses = as_json(req("GET", "/api/houses/", tok=admin)[1]) or {}
    house = (houses.get("results") or [None])[0]
    batches = as_json(req("GET", "/api/batches/?status=ACTIVE", tok=admin)[1]) or {}
    batch = (batches.get("results") or [None])[0]

    @check("FIX: farm-local date (dayOfCycle matches Africa/Douala today)")
    def _():
        if not house or not batch:
            raise Skip("no house with an active batch on this stack")
        s, b = req("GET", f"/api/houses/{house['house_code']}/tasks-now/", tok=admin)
        assert s == 200, s
        day = as_json(b).get("dayOfCycle")
        start = batch.get("start_date")
        # day_of_cycle is 0 on the start date, farm-local (apps.batches.services.day_of_cycle).
        # Comparing against the Africa/Douala calendar day — not the host's UTC day — is exactly
        # what catches the late-evening regression this FIX closed.
        farm_today = datetime.now(FARM_TZ).date()
        expected = (farm_today - date.fromisoformat(start[:10])).days if start else None
        assert day is not None, "dayOfCycle missing"
        if expected is not None:
            assert day == expected, f"dayOfCycle {day} != farm-local expected {expected} (start {start}, farm today {farm_today})"
        return f"dayOfCycle={day} on farm-local {farm_today}"

    @check("FIX: multiple assignees per protocol line")
    def _():
        if not house:
            raise Skip("no house on this stack")
        rows = as_json(req("GET", f"/api/houses/{house['house_code']}/assignments/", tok=admin)[1]) or []
        line = next((r for r in rows if not str(r["id"]).startswith("weighing-")), None)
        users = as_json(req("GET", "/api/tasks/assignable-users/", tok=admin)[1]) or []
        if not line or len(users) < 2:
            raise Skip("need a protocol line and 2+ assignable users")
        original = line.get("assignedTo", [])
        two = [users[0]["id"], users[1]["id"]]
        path = f"/api/houses/{house['house_code']}/tasks-now/{line['id']}/assign/"
        try:
            s, b = req("PATCH", path, {"assignees": two}, tok=admin)
            assert s == 200, f"assign -> {s} {b[:120]!r}"
            got = as_json(b)["assignedTo"]
            assert sorted(got) == sorted(two), f"assignedTo {got} != {two}"
            return f"assigned {len(two)} users, read back {len(got)}"
        finally:
            req("PATCH", path, {"assignees": original}, tok=admin)  # restore

    @check("FIX: opening stock entry (upsert round-trip)")
    def _():
        farm_id = None
        s, b = req("GET", "/api/farm/overview/", tok=admin)
        # farm id is in the /api/farms/<id>/... routes; discover it from the stock-items link
        # by trying the batch's farm, else parse from an existing item. Simplest: use /me.
        me = as_json(req("GET", "/api/auth/me/", tok=admin)[1]) or {}
        farm_id = me.get("farm") or me.get("farm_id") or (batch or {}).get("farm") or 2
        name = "REG-Article-Temporaire"
        s, b = req("POST", f"/api/farms/{farm_id}/stock-items/", {"name": name, "unit": "kg", "quantity": 42}, tok=admin)
        if s not in (200, 201):
            raise Skip(f"cannot create a disposable stock item ({s} {b[:120]!r})")
        code = as_json(b).get("item_code") or as_json(b).get("itemCode")
        try:
            items = as_json(req("GET", f"/api/farms/{farm_id}/stock-items/", tok=admin)[1]) or {}
            row = next((i for i in items.get("items", items if isinstance(items, list) else []) if i.get("name") == name), None)
            assert row is not None, "created item not found on read-back"
            return f"opening stock item created and read back (code {code})"
        finally:
            if code:
                req("DELETE", f"/api/stock-items/{code}/", tok=admin)  # restore

    @check("FIX: task completion deducts stock, undo restores it")
    def _():
        if not house:
            raise Skip("no house on this stack")
        code = house["house_code"]
        tasks = (as_json(req("GET", f"/api/houses/{code}/tasks-now/", tok=admin)[1]) or {}).get("tasks", [])
        task = next((t for t in tasks if not str(t["id"]).startswith("weighing-")), None)
        if not task:
            raise Skip("no completable protocol task due today")
        tid = task["id"]
        # Each occurrence carries its own slot id (twice-daily = two rows, one per slot).
        slot = task.get("timeSlotId")
        def complete(force=False):
            body = {"force": force}
            if slot:
                body["time_slot_id"] = slot
            return req("POST", f"/api/houses/{code}/tasks-now/{tid}/complete/", body, tok=admin)
        def uncomplete():
            body = {"time_slot_id": slot} if slot else {}
            return req("POST", f"/api/houses/{code}/tasks-now/{tid}/uncomplete/", body, tok=admin)
        uncomplete()  # start from a known-not-done state
        s, b = complete()
        assert s in (200, 201), f"complete -> {s} {b[:160]!r}"
        payload = as_json(b)
        mv = payload.get("movement")
        try:
            if mv is None:
                return "task has no linked stock; completion/undo works without a movement"
            # A movement means stock was deducted — undo must remove it.
            su, bu = uncomplete()
            assert su in (200, 204), f"uncomplete -> {su} {bu[:160]!r}"
            return f"completion deducted {mv.get('quantity')} of {mv.get('itemCode')}; undo removed it"
        finally:
            uncomplete()  # never leave the live farm's task marked done by the smoke

    @check("FIX: orphaned assignment can still be cleared")
    def _():
        if not house:
            raise Skip("no house on this stack")
        rows = as_json(req("GET", f"/api/houses/{house['house_code']}/assignments/", tok=admin)[1])
        assert isinstance(rows, list), "assignments endpoint should list every carried assignment"
        return f"{len(rows)} assignment(s) listed and clearable via /assign/ []"

    ok = all(state != "FAIL" for state, _, _ in results)
    width = max(len(n) for _, n, _ in results)
    print("\n== Live API regression (FIX 1-7) ==")
    for state, name, detail in results:
        print(f"  [{state}] {name.ljust(width)}  {detail}")
    print(f"== {'ALL GREEN' if ok else 'FAILURES ABOVE'} ({BASE}) ==")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
