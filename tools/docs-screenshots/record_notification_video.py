#!/usr/bin/env python3
"""Records a short real-browser video of the notification bell: log in to the demo farm
capture.py just created in this same CI job, open the bell, show the panel floating above the
page for a few seconds, close it. Playwright's native video recording (not a screen capture of
the agent's own terminal — there is no such thing to record; this is the real rendered app).

Must run *after* capture.py in the same job: it logs in to the farm capture.py already created
(Farm is a DB-enforced singleton, so this script never signs up its own) and relies on the one
LOW_STOCK alert capture.py seeded still being present (nothing in the flow below marks it read).

Usage: python record_notification_video.py <frontend_base_url> <out_dir>
"""
import argparse
import os
import shutil
from pathlib import Path

from playwright.sync_api import sync_playwright

VIEWPORT = {"width": 1440, "height": 900}
EMAIL = "admin@ferme-demo.local"
PASSWORD = "DemoFerme123!"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("out_dir")
    args = parser.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    video_dir = out / "_video_tmp"
    video_dir.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        context = browser.new_context(viewport=VIEWPORT, record_video_dir=str(video_dir), record_video_size=VIEWPORT)
        page = context.new_page()

        page.goto(f"{args.base_url}/login", wait_until="networkidle")
        page.get_by_label("Email").fill(EMAIL)
        page.get_by_label("Mot de passe").fill(PASSWORD)
        page.get_by_role("button", name="Se connecter").click()
        page.wait_for_url(f"{args.base_url}/dashboard*", timeout=15000)
        page.wait_for_timeout(800)

        bell = page.get_by_role("button", name="Notifications")
        bell.scroll_into_view_if_needed()
        page.wait_for_timeout(500)
        bell.click()
        page.wait_for_timeout(2500)  # hold the open panel on screen
        # Scroll the page under the fixed panel to prove it stays anchored, not painted once.
        page.mouse.wheel(0, 300)
        page.wait_for_timeout(1500)

        video_path = page.video.path() if page.video else None
        context.close()
        browser.close()

        if video_path and Path(video_path).exists():
            dest = out / "45-notification-bell-ouverte.webm"
            shutil.move(video_path, dest)
            print(f"  captured {dest.name}")
        else:
            print("  FAILED: no video produced")
        shutil.rmtree(video_dir, ignore_errors=True)

    print(f"Done — video in {out}")


if __name__ == "__main__":
    main()
