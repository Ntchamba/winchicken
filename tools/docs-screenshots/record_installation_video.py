#!/usr/bin/env python3
"""Records a single continuous, realistically-paced (~3-4 min) video of a real, from-scratch
farm installation: the actual "Créer une ferme" signup form, through onboarding, to a short
tour of the resulting dashboard — against a freshly migrated, UNSEEDED database (own CI job,
own ephemeral Postgres/Redis, never seed_test_farm).

Unlike capture.py's onboarding walk-through, the protocol step here clicks "Charger le modèle
de départ" instead of typing one line by hand — the researched poulet-de-chair J1-J56 template
is loaded through the real button, same as any user would. Per the cahier des charges (7.3,
"no-default-data rule"), the app never pre-fills this on its own; this script only ever clicks
the same button a human would.

Deliberately slow and thorough (long pauses, every category tab visited, a post-onboarding tour
of a few real pages) rather than a quick click-through — the first cut of this video was 15
seconds and showed one field; this one holds each screen long enough to actually read.

Everything in onboarding itself is still the minimum a first-time user must do by hand (one
house, one stock article — "Suivant" is blocked on empty stock — employees skipped): no extra
demo data layered on top, only a longer, fuller look at what's already there.

Usage: python record_installation_video.py <frontend_base_url> <out_dir>
"""
import argparse
import os
import shutil
from pathlib import Path

from playwright.sync_api import sync_playwright

VIEWPORT = {"width": 1440, "height": 900}
ADMIN_NAME = "Jean Mbarga"
EMAIL = "admin@ferme-demo.local"
PASSWORD = "DemoFerme123!"
FARM_NAME = "Ferme Avicole Démo"
BUILDING_NAME = "Bâtiment A"
BATCH_NAME = "Bande de démonstration"
CHICKS_PLACED = "500"
STOCK_ARTICLE = "Aliment démarrage"

# All 5 default categories, in DEFAULT_CATEGORIES order (utils/protocolRows.js) — every one of
# them carries real rows from STARTER_TEMPLATE, so the tour visits every tab, not just a few.
CATEGORY_TABS = ["Alimentation", "Température", "Santé et soins", "Vaccination", "Nettoyage"]


def slow_fill(page, label, value, pause_ms=1800):
    page.get_by_label(label).click()
    page.get_by_label(label).fill(value)
    page.wait_for_timeout(pause_ms)


def record_installation(page, base_url):
    # --- The signup form itself: landing on it, then filling each field with a visible pause. ---
    page.goto(f"{base_url}/create-farm", wait_until="networkidle")
    page.wait_for_timeout(5000)
    slow_fill(page, "Nom de l'administrateur", ADMIN_NAME)
    slow_fill(page, "Email", EMAIL)
    slow_fill(page, "Mot de passe", PASSWORD)
    slow_fill(page, "Nom de la ferme", FARM_NAME)
    page.wait_for_timeout(5000)
    page.get_by_role("button", name="Créer une ferme").click()
    page.wait_for_url(f"{base_url}/onboarding/protocol*", timeout=20000)
    page.wait_for_timeout(1500)  # the 300ms TransitionScreen, held much longer on video

    # --- Step 1/4: batch header. ---
    page.wait_for_timeout(1500)
    slow_fill(page, "Nom de la bande", BATCH_NAME)
    slow_fill(page, "Poussins mis en place", CHICKS_PLACED)
    slow_fill(page, "Nom du bâtiment", BUILDING_NAME)
    page.wait_for_timeout(4000)
    page.get_by_role("button", name="Suivant").click()

    # --- Step 2/4: manual vs Excel — pause on both options before picking. ---
    page.wait_for_timeout(2500)
    page.get_by_role("button", name="Configurer manuellement").click()

    # --- Step 3/4: the protocol form — load the real default template through the real button,
    # exactly as a user would (never auto-loaded — cahier des charges 7.3), then actually tour
    # every one of the 5 category tabs so every field category is visibly on screen (~90s here). ---
    page.wait_for_timeout(2000)
    page.get_by_role("button", name="Charger le modèle de départ").click()
    page.wait_for_timeout(4000)
    for tab_name in CATEGORY_TABS:
        page.get_by_role("button", name=tab_name, exact=False).first.click()
        page.wait_for_timeout(3000)
        # Scroll through this category's rows so lines past the first are visible too.
        page.mouse.wheel(0, 450)
        page.wait_for_timeout(4000)
        page.mouse.wheel(0, 450)
        page.wait_for_timeout(4000)
        page.mouse.wheel(0, 450)
        page.wait_for_timeout(3000)
        page.mouse.wheel(0, -1500)
        page.wait_for_timeout(1200)
    page.wait_for_timeout(1500)
    page.get_by_role("button", name="Suivant", exact=True).click()
    page.wait_for_url(f"{base_url}/onboarding/stock*", timeout=15000)

    # --- Step 4/4-ish: opening stock — needs at least one article (empty stock blocks "Suivant"). ---
    page.wait_for_timeout(4000)
    page.get_by_role("button", name="Ajouter un article").click()
    page.wait_for_timeout(1000)
    page.get_by_placeholder("Nom de l'article").fill(STOCK_ARTICLE)
    page.wait_for_timeout(5000)
    page.get_by_role("button", name="Suivant", exact=True).click()
    page.wait_for_url(f"{base_url}/onboarding/employees*", timeout=15000)

    # --- Employees: skipped — a fresh farm has no staff accounts yet either. ---
    page.wait_for_timeout(5000)
    page.get_by_role("button", name="Sauter").click()
    page.wait_for_url(f"{base_url}/dashboard*", timeout=15000)
    page.wait_for_timeout(5500)

    # --- Tour of the real, just-created farm: overview, the house's saved protocol (proving
    # the template was actually persisted, not just shown mid-onboarding), tasks, and stock. ---
    page.mouse.wheel(0, 500)
    page.wait_for_timeout(3000)
    page.mouse.wheel(0, 500)
    page.wait_for_timeout(3000)
    page.mouse.wheel(0, -1200)
    page.wait_for_timeout(1200)

    house_buttons = page.locator("nav.sidebar-nav button.sidebar-link")
    if house_buttons.count() > 0:
        house_buttons.first.click()
        page.wait_for_url("**/dashboard/houses/*", timeout=10000)
        page.wait_for_timeout(3500)
        house_code = page.url.rstrip("/").split("/")[-1]
        house_path = f"/dashboard/houses/{house_code}"

        page.goto(f"{base_url}{house_path}/protocol", wait_until="networkidle")
        page.wait_for_timeout(3000)
        for tab_name in ["Alimentation", "Vaccination", "Nettoyage", "Santé et soins"]:
            page.get_by_role("button", name=tab_name, exact=False).first.click()
            page.wait_for_timeout(4000)

        page.goto(f"{base_url}{house_path}/tasks", wait_until="networkidle")
        page.wait_for_timeout(7000)
        page.mouse.wheel(0, 400)
        page.wait_for_timeout(2500)

    page.goto(f"{base_url}/dashboard/stock", wait_until="networkidle")
    page.wait_for_timeout(6000)
    page.mouse.wheel(0, 400)
    page.wait_for_timeout(3000)

    page.goto(f"{base_url}/dashboard", wait_until="networkidle")
    page.wait_for_timeout(9000)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("out_dir")
    args = parser.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    video_dir = out / "_install_video_tmp"
    video_dir.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        context = browser.new_context(viewport=VIEWPORT, record_video_dir=str(video_dir), record_video_size=VIEWPORT)
        page = context.new_page()
        page.on("console", lambda m: print(f"  [console {m.type}] {m.text}") if m.type == "error" else None)

        print("Recording a from-scratch farm installation (slow, thorough pass)…")
        record_installation(page, args.base_url)

        video_path = page.video.path() if page.video else None
        context.close()
        browser.close()

        if video_path and Path(video_path).exists():
            dest = out / "65-installation-ferme-complete.webm"
            shutil.move(video_path, dest)
            print(f"  captured {dest.name}")
        else:
            print("  FAILED: no video produced")
        shutil.rmtree(video_dir, ignore_errors=True)

    print(f"Done — video in {out}")


if __name__ == "__main__":
    main()
