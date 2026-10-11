#!/usr/bin/env python3
"""Records a single continuous video of a real, from-scratch farm installation: the actual
"Créer une ferme" signup form, through onboarding, to the dashboard — against a freshly
migrated, UNSEEDED database (own CI job, own ephemeral Postgres/Redis, never seed_test_farm).

Unlike capture.py's onboarding walk-through, the protocol step here clicks "Charger le modèle
de départ" instead of typing one line by hand — the researched poulet-de-chair J1-J56 template
is loaded through the real button, same as any user would. Per the cahier des charges (7.3,
"no-default-data rule"), the app never pre-fills this on its own; this script only ever clicks
the same button a human would.

Everything else is the minimum a first-time user must do by hand (one house, one stock article —
"Suivant" is blocked on empty stock — employees skipped): no extra demo data layered on top.

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


def record_installation(page, base_url):
    page.goto(f"{base_url}/create-farm", wait_until="networkidle")
    page.wait_for_timeout(600)
    page.get_by_label("Nom de l'administrateur").fill(ADMIN_NAME)
    page.get_by_label("Email").fill(EMAIL)
    page.get_by_label("Mot de passe").fill(PASSWORD)
    page.get_by_label("Nom de la ferme").fill(FARM_NAME)
    page.wait_for_timeout(500)
    page.get_by_role("button", name="Créer une ferme").click()
    page.wait_for_url(f"{base_url}/onboarding/protocol*", timeout=20000)
    page.wait_for_timeout(800)  # the 300ms TransitionScreen, held a bit longer on video

    # Step 1/4: batch header.
    page.get_by_label("Nom de la bande").fill(BATCH_NAME)
    page.get_by_label("Poussins mis en place").fill(CHICKS_PLACED)
    page.get_by_label("Nom du bâtiment").fill(BUILDING_NAME)
    page.wait_for_timeout(500)
    page.get_by_role("button", name="Suivant").click()

    # Step 2/4: manual vs Excel — "Configurer manuellement" to reach the protocol form itself.
    page.wait_for_timeout(500)
    page.get_by_role("button", name="Configurer manuellement").click()

    # Step 3/4: the protocol form — load the real default template through the real button,
    # exactly as a user would (never auto-loaded — cahier des charges 7.3).
    page.wait_for_timeout(600)
    page.get_by_role("button", name="Charger le modèle de départ").click()
    page.wait_for_timeout(600)
    # Walk through a couple of category tabs so the loaded rows are visibly on screen.
    for tab_name in ["Température", "Vaccination", "Alimentation"]:
        page.get_by_role("button", name=tab_name, exact=False).first.click()
        page.wait_for_timeout(900)
    page.wait_for_timeout(500)
    page.get_by_role("button", name="Suivant", exact=True).click()
    page.wait_for_url(f"{base_url}/onboarding/stock*", timeout=15000)

    # Step 4/4-ish: opening stock — needs at least one article (empty stock blocks "Suivant").
    page.wait_for_timeout(600)
    page.get_by_role("button", name="Ajouter un article").click()
    page.get_by_placeholder("Nom de l'article").fill(STOCK_ARTICLE)
    page.wait_for_timeout(500)
    page.get_by_role("button", name="Suivant", exact=True).click()
    page.wait_for_url(f"{base_url}/onboarding/employees*", timeout=15000)

    # Employees: skipped — a fresh farm has no staff accounts yet either.
    page.wait_for_timeout(500)
    page.get_by_role("button", name="Sauter").click()
    page.wait_for_url(f"{base_url}/dashboard*", timeout=15000)
    page.wait_for_timeout(1500)  # hold on the finished dashboard


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

        print("Recording a from-scratch farm installation…")
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
