#!/usr/bin/env python3
"""Logs into a running Winchicken instance through the real UI and screenshots every major
screen, for the documentation (HTML site + PDF manual). Run only against the seeded test stack
(seed_test_farm) — never against a real farm's data.

Usage: python capture.py <frontend_base_url> <out_dir> [--email E] [--password P]
"""
import argparse
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

VIEWPORT = {"width": 1440, "height": 900}


def login(page, base_url, email, password):
    page.goto(f"{base_url}/login", wait_until="networkidle")
    page.screenshot(path=str(OUT / "00-login.png"), full_page=True)
    page.get_by_label("Email").fill(email)
    page.get_by_label("Mot de passe").fill(password)
    page.get_by_role("button", name="Se connecter").click()
    page.wait_for_url(f"{base_url}/dashboard*", timeout=15000)
    # The 300ms TransitionScreen between login and the dashboard.
    page.wait_for_timeout(600)


def shot(page, base_url, path, name, wait_selector=None, wait_ms=500):
    page.goto(f"{base_url}{path}", wait_until="networkidle")
    if wait_selector:
        try:
            page.wait_for_selector(wait_selector, timeout=5000)
        except Exception:
            pass
    page.wait_for_timeout(wait_ms)
    page.screenshot(path=str(OUT / name), full_page=True)
    print(f"  captured {name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("out_dir")
    parser.add_argument("--email", default="admin@test.local")
    parser.add_argument("--password", default="TestVerify123!")
    args = parser.parse_args()

    global OUT
    OUT = Path(args.out_dir)
    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        # CI installs its own matching browser via `playwright install chromium`; this override
        # is only for a local dry run against a pre-existing Chromium (e.g. a dev sandbox).
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        page = browser.new_page(viewport=VIEWPORT)
        page.on("console", lambda m: print(f"  [console {m.type}] {m.text}") if m.type == "error" else None)

        print("Logging in…")
        login(page, args.base_url, args.email, args.password)

        pages = [
            ("/dashboard", "01-dashboard-accueil.png", None),
            ("/dashboard/overview", "02-bilan-global.png", None),
            ("/dashboard/houses", "03-batiments-liste.png", None),
            ("/dashboard/finances", "10-finances.png", None),
            ("/dashboard/stock", "20-stock.png", None),
            ("/dashboard/purchase-orders", "21-commandes-fournisseurs.png", None),
            ("/dashboard/employees", "30-employes.png", None),
            ("/dashboard/cashier", "31-caisse.png", None),
            ("/dashboard/alerts", "40-alertes.png", None),
            ("/dashboard/calendar", "41-calendrier.png", None),
            ("/dashboard/my-tasks", "42-mes-taches.png", None),
            ("/dashboard/audit", "43-journal-audit.png", None),
            ("/dashboard/settings", "44-parametres.png", None),
        ]
        for path, name, sel in pages:
            try:
                shot(page, args.base_url, path, name, sel)
            except Exception as e:
                print(f"  FAILED {name}: {e}")

        # House detail pages need a real house code — the sidebar's "Bâtiments" section (present
        # on every dashboard page) renders each as a <button onClick> (DashboardLayout.jsx), not
        # a plain <a href>, so a URL click + page.url() read is the reliable way to get one
        # rather than hardcoding a code the seed data might change.
        house_buttons = page.locator("nav.sidebar-nav button.sidebar-link")
        count = house_buttons.count()
        print(f"Found {count} house sidebar button(s)")
        if count > 0:
            house_buttons.first.click()
            page.wait_for_url("**/dashboard/houses/*", timeout=10000)
            house_code = page.url.rstrip("/").split("/")[-1]
            house_path = f"/dashboard/houses/{house_code}"
            for sub, name in [
                ("", "50-batiment-detail.png"),
                ("/protocol", "51-batiment-protocole.png"),
                ("/tasks", "52-batiment-taches.png"),
                ("/weighing", "53-batiment-pesees.png"),
                ("/cases", "54-batiment-cas.png"),
                ("/evolution", "55-batiment-evolution.png"),
            ]:
                target = f"{house_path}{sub}"
                try:
                    shot(page, args.base_url, target, name)
                except Exception as e:
                    print(f"  FAILED {name}: {e}")

        browser.close()
    print(f"Done — screenshots in {OUT}")


if __name__ == "__main__":
    main()
