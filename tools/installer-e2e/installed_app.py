#!/usr/bin/env python3
"""Uses the app the launcher just installed, like a farm would on day one: creates the farm
through the real "Créer une ferme" form, runs onboarding loading the default protocol with
"Charger le modèle de départ", lands on the dashboard; then opens the installed /demo page to
check it ships the J1-J56 template. Every screenshot comes from the production stack (nginx +
gunicorn + Postgres) built into the .exe — not a dev server.

Usage: python installed_app.py <app_url> <out_dir>
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

base, out = sys.argv[1].rstrip("/"), Path(sys.argv[2])


def fill(page, label, value):
    page.get_by_label(label).fill(value)


with sync_playwright() as p:
    page = p.chromium.launch().new_page(viewport={"width": 1440, "height": 900})
    page.on("console", lambda m: print(f"[console {m.type}] {m.text}") if m.type == "error" else None)

    page.goto(f"{base}/create-farm", wait_until="networkidle")
    fill(page, "Nom de l'administrateur", "Jean Mbarga")
    fill(page, "Email", "admin@ferme-demo.local")
    fill(page, "Mot de passe", "DemoFerme123!")
    fill(page, "Nom de la ferme", "Ferme Avicole Démo")
    page.get_by_role("button", name="Créer une ferme").click()
    page.wait_for_url(f"{base}/onboarding/protocol*", timeout=30000)
    page.wait_for_timeout(800)

    fill(page, "Nom de la bande", "Bande de démonstration")
    fill(page, "Poussins mis en place", "500")
    fill(page, "Nom du bâtiment", "Bâtiment A")
    page.get_by_role("button", name="Suivant").click()
    page.wait_for_timeout(500)
    page.get_by_role("button", name="Configurer manuellement").click()
    page.wait_for_timeout(500)
    page.get_by_role("button", name="Charger le modèle de départ").click()
    page.wait_for_timeout(800)
    page.screenshot(path=str(out / "linux-3-protocole-modele-charge.png"))
    page.get_by_role("button", name="Suivant", exact=True).click()
    page.wait_for_url(f"{base}/onboarding/stock*", timeout=20000)
    page.wait_for_timeout(500)
    page.get_by_role("button", name="Ajouter un article").click()
    page.get_by_placeholder("Nom de l'article").fill("Aliment démarrage")
    page.get_by_role("button", name="Suivant", exact=True).click()
    page.wait_for_url(f"{base}/onboarding/employees*", timeout=20000)
    page.wait_for_timeout(500)
    page.get_by_role("button", name="Sauter").click()
    page.wait_for_url(f"{base}/dashboard*", timeout=20000)
    page.wait_for_timeout(2500)
    page.screenshot(path=str(out / "linux-4-application-installee.png"))

    page.goto(f"{base}/demo", wait_until="networkidle")
    page.get_by_role("button", name="Protocole du bâtiment").click()
    page.wait_for_timeout(1200)
    page.screenshot(path=str(out / "linux-5-demo-installee.png"))
    # Protocol rows are editable inputs, so the template's text lives in their values, not the DOM text.
    rows = page.evaluate("() => [...document.querySelectorAll('input')].filter(i => i.value.includes('Aliment démarrage')).length")
    print(f"/demo protocol inputs containing 'Aliment démarrage': {rows}")
    if rows == 0:
        sys.exit("installed /demo page does not show the J1-J56 template")
