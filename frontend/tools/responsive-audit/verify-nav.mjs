#!/usr/bin/env node
/**
 * Live check for the mobile navigation drawer (2026-09-18 audit, finding 1).
 *
 * The audit measures a page at rest; this one drives it. At each width it opens the drawer,
 * follows a link that exists nowhere else, and closes it again — because "the button renders"
 * and "a worker can reach Paramètres from a phone" are not the same claim.
 *
 *   npm run verify:nav
 *   npm run verify:nav -- --widths=375
 */
import { launch } from "./cdp.mjs";

const arg = (name, fallback) => {
  const hit = process.argv.find((a) => a.startsWith(`--${name}=`));
  return hit ? hit.slice(name.length + 3) : fallback;
};

const BASE = arg("base", process.env.BASE_URL || "http://localhost:5180");
const API = arg("api", process.env.API_URL || "http://localhost:8010");
const WIDTHS = arg("widths", "375,768,1440").split(",").map(Number);
const EMAIL = process.env.AUDIT_ADMIN || "admin@test.local";
const PASSWORD = process.env.AUDIT_ADMIN_PW || "TestVerify123!";

/** Links that live only in the drawer — the ones finding (1) made unreachable. */
const DRAWER_ONLY = ["Finances", "Stock", "Employés", "Paramètres", "Déconnexion", "Mes heures"];

const results = [];
const check = (width, name, pass, detail) => {
  results.push({ width, name, pass, detail });
  console.log(`  ${pass ? "PASS" : "FAIL"}  ${name}${detail ? ` — ${detail}` : ""}`);
};

const state = `
  const toggle = document.getElementById('sidebar-mobile-toggle');
  const sidebar = document.getElementById('dashboard-sidebar');
  const scrim = document.querySelector('.sidebar-scrim');
  const rect = sidebar.getBoundingClientRect();
  const toggleRect = toggle ? toggle.getBoundingClientRect() : null;
  const labels = Array.from(sidebar.querySelectorAll('button, a')).map((el) => (el.textContent || '').trim());
  return {
    toggleRendered: !!toggle && toggle.getClientRects().length > 0,
    toggleBox: toggleRect ? { w: Math.round(toggleRect.width), h: Math.round(toggleRect.height) } : null,
    toggleExpanded: toggle ? toggle.getAttribute('aria-expanded') : null,
    sidebarLeft: Math.round(rect.left),
    sidebarOnScreen: rect.right > 0 && rect.left < window.innerWidth,
    scrimRendered: !!scrim && scrim.getClientRects().length > 0,
    bodyOverflow: getComputedStyle(document.body).overflow,
    labels,
    path: location.pathname,
  };
`;

async function run() {
  const res = await fetch(`${API}/api/auth/login/`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });
  if (!res.ok) throw new Error(`login failed: ${res.status}`);
  const tokens = await res.json();

  const browser = await launch();
  try {
    await browser.onNewDocument(
      `try { localStorage.setItem('winchicken_tokens', ${JSON.stringify(
        JSON.stringify({ access: tokens.access, refresh: tokens.refresh }),
      )}); } catch (e) {}`,
    );

    for (const width of WIDTHS) {
      const phone = width < 900;
      console.log(`\n=== ${width}px (${phone ? "drawer expected" : "sidebar always on screen"}) ===`);
      await browser.setViewport(width, 812, { mobile: phone });
      await browser.goto(`${BASE}/dashboard`);

      const closed = await browser.eval(state);

      if (!phone) {
        check(width, "no menu button above the drawer breakpoint", !closed.toggleRendered);
        check(width, "sidebar is on screen without opening anything", closed.sidebarOnScreen, `left=${closed.sidebarLeft}`);
        continue;
      }

      check(width, "menu button is rendered", closed.toggleRendered);
      check(
        width,
        "menu button meets the 44px tap target",
        closed.toggleBox && closed.toggleBox.w >= 44 && closed.toggleBox.h >= 44,
        closed.toggleBox && `${closed.toggleBox.w}x${closed.toggleBox.h}`,
      );
      check(width, "drawer starts off screen", !closed.sidebarOnScreen, `left=${closed.sidebarLeft}`);
      check(width, "aria-expanded starts false", closed.toggleExpanded === "false");

      await browser.eval("document.getElementById('sidebar-mobile-toggle').click(); return true;");
      await browser.eval("return new Promise((r) => setTimeout(r, 400));");
      const open = await browser.eval(state);

      check(width, "drawer slides on screen", open.sidebarOnScreen, `left=${open.sidebarLeft}`);
      check(width, "aria-expanded flips to true", open.toggleExpanded === "true");
      check(width, "scrim covers the page", open.scrimRendered);
      check(width, "page scrolling is locked behind it", open.bodyOverflow === "hidden");
      const missing = DRAWER_ONLY.filter((label) => !open.labels.some((l) => l.includes(label)));
      check(width, "every drawer-only link is present", missing.length === 0, missing.length ? `absent: ${missing.join(", ")}` : DRAWER_ONLY.join(", "));

      // The claim under test is navigation, not rendering: tap Paramètres and land on it.
      await browser.eval(`
        const target = Array.from(document.querySelectorAll('#dashboard-sidebar button'))
          .find((b) => (b.textContent || '').trim().includes('Paramètres'));
        target.click();
        return true;
      `);
      await browser.eval("return new Promise((r) => setTimeout(r, 700));");
      const navigated = await browser.eval(state);
      check(width, "tapping Paramètres navigates there", navigated.path === "/dashboard/settings", navigated.path);
      check(width, "drawer closes behind the navigation", !navigated.sidebarOnScreen, `left=${navigated.sidebarLeft}`);
      check(width, "page scrolling is restored", navigated.bodyOverflow !== "hidden", navigated.bodyOverflow);

      // Scrim close, from a fresh open.
      await browser.eval("document.getElementById('sidebar-mobile-toggle').click(); return true;");
      await browser.eval("return new Promise((r) => setTimeout(r, 400));");
      await browser.eval("document.querySelector('.sidebar-scrim').click(); return true;");
      await browser.eval("return new Promise((r) => setTimeout(r, 400));");
      const scrimmed = await browser.eval(state);
      check(width, "tapping the dimmed page closes the drawer", !scrimmed.sidebarOnScreen, `left=${scrimmed.sidebarLeft}`);
    }
  } finally {
    await browser.close();
  }

  const failed = results.filter((r) => !r.pass);
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
  if (failed.length) {
    for (const f of failed) console.log(`  FAIL ${f.width}px ${f.name} ${f.detail || ""}`);
    process.exit(1);
  }
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
