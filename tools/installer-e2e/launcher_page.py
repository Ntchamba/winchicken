#!/usr/bin/env python3
"""Screenshots the real launcher's setup page (http://127.0.0.1:47823) while it installs.

windows: Docker Desktop cannot run on GitHub's Windows runners, so the expected end state is the
         "Docker n'est pas installé" problem card — captured as the last Windows screenshot.
linux:   Docker is there, so the launcher must reach "Winchicken est prêt"; the app's local URL
         is written to <out>/local_url.txt for the next step. Fails the job if it never does.

Usage: python launcher_page.py <launcher_url> <out_dir> windows|linux
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

base, out, mode = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
out.mkdir(parents=True, exist_ok=True)


def status():
    try:
        with urllib.request.urlopen(f"{base}/status", timeout=3) as r:
            return json.load(r)
    except Exception:
        return None


deadline = time.time() + 60
while status() is None:
    if time.time() > deadline:
        sys.exit("launcher never answered on " + base)
    time.sleep(1)

with sync_playwright() as p:
    page = p.chromium.launch().new_page(viewport={"width": 1280, "height": 900})
    page.goto(base, wait_until="networkidle")
    page.wait_for_timeout(1500)
    page.screenshot(path=str(out / f"{mode}-1-installation-en-cours.png"), full_page=True)

    deadline = time.time() + (25 * 60 if mode == "linux" else 3 * 60)
    s = status()
    while time.time() < deadline:
        s = status() or s
        if s.get("ready") or s.get("problem"):
            break
        time.sleep(3)
    print(json.dumps(s, ensure_ascii=False, indent=1)[:4000])

    page.wait_for_timeout(2000)
    if s.get("ready"):
        page.locator("#stay").click()  # stop the 15 s auto-redirect so the card can be captured
        page.wait_for_timeout(800)
        page.screenshot(path=str(out / f"{mode}-2-winchicken-pret.png"), full_page=True)
        (out / "local_url.txt").write_text(s["ready"]["localUrl"])
    else:
        page.screenshot(path=str(out / f"{mode}-2-etat-final.png"), full_page=True)

if mode == "linux" and not s.get("ready"):
    sys.exit("launcher did not reach 'Winchicken est prêt'")
