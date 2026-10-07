#!/usr/bin/env python3
"""Drives a *freshly migrated, unseeded* Winchicken instance through the real "Créer une ferme"
signup and onboarding flow (farm -> batch header -> protocol -> opening stock -> skip employees),
then screenshots every major screen for the documentation (HTML site + PDF manual).

Deliberately does NOT use `seed_test_farm`: that command backfills a farm with two houses, daily
logs, weighings and stock history, which looks nothing like what a real first-time user sees.
This script enters the minimum a human must enter by hand to reach the dashboard (one house, one
batch, one protocol line, one stock article) and adds no history at all — mortality, sales,
weighings stay at zero, exactly as they are the day a real farm is created.

Usage: python capture.py <frontend_base_url> <out_dir>
"""
import argparse
import sys
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

VIEWPORT = {"width": 1440, "height": 2000}

ADMIN_NAME = "Jean Mbarga"
EMAIL = "admin@ferme-demo.local"
PASSWORD = "DemoFerme123!"
FARM_NAME = "Ferme Avicole Démo"
BUILDING_NAME = "Bâtiment A"
BATCH_NAME = "Bande de démonstration"
CHICKS_PLACED = "500"
PROTOCOL_ACTION = "Aliment démarrage"
PROTOCOL_DETAILS = "3000 kcal, 22,5% de protéines"
STOCK_ARTICLE = "Aliment démarrage"


def shot(page, name, wait_ms=500):
    page.wait_for_timeout(wait_ms)
    page.screenshot(path=str(OUT / name), full_page=False)
    print(f"  captured {name}")


def create_farm_and_onboard(page, base_url):
    """Signs up through the real form, then fills the minimum onboarding needs by hand."""
    page.goto(f"{base_url}/create-farm", wait_until="networkidle")
    page.get_by_label("Nom de l'administrateur").fill(ADMIN_NAME)
    page.get_by_label("Email").fill(EMAIL)
    page.get_by_label("Mot de passe").fill(PASSWORD)
    page.get_by_label("Nom de la ferme").fill(FARM_NAME)
    page.get_by_role("button", name="Créer une ferme").click()
    page.wait_for_url(f"{base_url}/onboarding/protocol*", timeout=20000)
    page.wait_for_timeout(600)  # the 300ms TransitionScreen

    # Step 1/4: batch header.
    shot(page, "60-onboarding-bande.png")
    page.get_by_label("Nom de la bande").fill(BATCH_NAME)
    page.get_by_label("Poussins mis en place").fill(CHICKS_PLACED)
    page.get_by_label("Nom du bâtiment").fill(BUILDING_NAME)
    page.get_by_role("button", name="Suivant").click()

    # Step 2/4: manual vs Excel.
    page.wait_for_timeout(300)
    shot(page, "61-onboarding-methode.png")
    page.get_by_role("button", name="Configurer manuellement").click()

    # Step 3/4: the protocol form itself — one real line, no more.
    page.wait_for_timeout(300)
    shot(page, "62-onboarding-protocole.png")
    page.get_by_role("button", name="Ajouter une ligne").click()
    page.get_by_label("Action").fill(PROTOCOL_ACTION)
    page.get_by_label("Détails").fill(PROTOCOL_DETAILS)
    page.get_by_role("button", name="Suivant", exact=True).click()
    page.wait_for_url(f"{base_url}/onboarding/stock*", timeout=15000)

    # Step 4/4-ish: opening stock — needs at least one article (empty stock blocks "Suivant").
    page.wait_for_timeout(500)
    shot(page, "63-onboarding-stock.png")
    page.get_by_role("button", name="Ajouter un article").click()
    page.get_by_placeholder("Nom de l'article").fill(STOCK_ARTICLE)
    page.get_by_role("button", name="Suivant", exact=True).click()
    page.wait_for_url(f"{base_url}/onboarding/employees*", timeout=15000)

    # Employees: skipped — a fresh farm has no staff accounts yet either.
    page.wait_for_timeout(400)
    shot(page, "64-onboarding-employes.png")
    page.get_by_role("button", name="Sauter").click()
    page.wait_for_url(f"{base_url}/dashboard*", timeout=15000)
    page.wait_for_timeout(600)


def shot_path(page, base_url, path, name, wait_ms=500):
    page.goto(f"{base_url}{path}", wait_until="networkidle")
    page.wait_for_timeout(wait_ms)
    page.screenshot(path=str(OUT / name), full_page=False)
    print(f"  captured {name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("out_dir")
    args = parser.parse_args()

    global OUT
    OUT = Path(args.out_dir)
    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        page = browser.new_page(viewport=VIEWPORT)
        page.on("console", lambda m: print(f"  [console {m.type}] {m.text}") if m.type == "error" else None)

        print("Signing up and onboarding (no seed data)…")
        create_farm_and_onboard(page, args.base_url)

        pages = [
            ("/dashboard", "01-dashboard-accueil.png", 500),
            ("/dashboard/overview", "02-bilan-global.png", 500),
            ("/dashboard/houses", "03-batiments-liste.png", 500),
            ("/dashboard/finances", "10-finances.png", 500),
            ("/dashboard/stock", "20-stock.png", 500),
            ("/dashboard/purchase-orders", "21-commandes-fournisseurs.png", 500),
            ("/dashboard/employees", "30-employes.png", 500),
            ("/dashboard/cashier", "31-caisse.png", 500),
            ("/dashboard/alerts", "40-alertes.png", 500),
            ("/dashboard/calendar", "41-calendrier.png", 500),
            ("/dashboard/my-tasks", "42-mes-taches.png", 500),
            ("/dashboard/audit", "43-journal-audit.png", 500),
            ("/dashboard/settings", "44-parametres.png", 500),
        ]
        for path, name, wait_ms in pages:
            try:
                shot_path(page, args.base_url, path, name, wait_ms)
            except Exception as e:
                print(f"  FAILED {name}: {e}")

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
                    shot_path(page, args.base_url, target, name)
                except Exception as e:
                    print(f"  FAILED {name}: {e}")

        browser.close()
    print(f"Done — screenshots in {OUT}")


if __name__ == "__main__":
    main()
