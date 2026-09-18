#!/usr/bin/env node
/**
 * Responsive audit: drives the real app in a real Chrome at several viewport widths and
 * measures what a phone user would actually hit.
 *
 * Why this lives in the repo and not in a scratchpad: the first run of this audit was lost to a
 * power cut along with its 86 screenshots, and re-deriving it cost a full session. One command,
 * committed, re-runnable.
 *
 *   npm run audit:responsive
 *   npm run audit:responsive -- --widths=375 --views=cashier,calendar
 *   npm run audit:responsive -- --role=worker --no-shots
 *
 * Defaults target the isolated test stack (UI :5180, API :8010). Point it elsewhere with
 * --base/--api or BASE_URL/API_URL.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { launch } from "./cdp.mjs";
import { PROBE } from "./probe.mjs";
import { adminViews, workerViews, publicViews, onboardingViews } from "./views.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "out");

const arg = (name, fallback) => {
  const hit = process.argv.find((a) => a.startsWith(`--${name}=`));
  return hit ? hit.slice(name.length + 3) : fallback;
};
const flag = (name) => process.argv.includes(`--${name}`);

const BASE = arg("base", process.env.BASE_URL || "http://localhost:5180");
const API = arg("api", process.env.API_URL || "http://localhost:8010");
const WIDTHS = arg("widths", "375,768,1440").split(",").map(Number);
const ROLES = arg("role", "all").split(",");
const ONLY = arg("views", "").split(",").filter(Boolean);
const SHOTS = !flag("no-shots");

const CREDENTIALS = {
  admin: { email: process.env.AUDIT_ADMIN || "admin@test.local", password: process.env.AUDIT_ADMIN_PW || "TestVerify123!" },
  worker: { email: process.env.AUDIT_WORKER || "ouvrier01@test.local", password: process.env.AUDIT_WORKER_PW || "FixVerify123!" },
};

/** Log in over the API so the audit never depends on the login form it is also measuring. */
async function login({ email, password }) {
  const res = await fetch(`${API}/api/auth/login/`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error(`login failed for ${email}: ${res.status} ${await res.text()}`);
  const body = await res.json();
  return { access: body.access, refresh: body.refresh };
}

async function firstHouseCode(tokens) {
  const res = await fetch(`${API}/api/houses/`, { headers: { authorization: `Bearer ${tokens.access}` } });
  if (!res.ok) return "H-1-001";
  const body = await res.json();
  const rows = Array.isArray(body) ? body : body.results || [];
  return rows[0]?.house_code || rows[0]?.houseCode || "H-1-001";
}

/** Seed the tokens before any app JS runs, so the app boots authenticated on first paint. */
const seedScript = (tokens) =>
  tokens
    ? `try { localStorage.setItem('winchicken_tokens', ${JSON.stringify(JSON.stringify(tokens))}); } catch (e) {}`
    : `try { localStorage.removeItem('winchicken_tokens'); } catch (e) {}`;

async function run() {
  mkdirSync(join(OUT, "shots"), { recursive: true });

  const adminTokens = await login(CREDENTIALS.admin);
  const houseCode = await firstHouseCode(adminTokens);
  let workerTokens = null;
  try {
    workerTokens = await login(CREDENTIALS.worker);
  } catch (err) {
    console.warn(`! worker login unavailable, skipping worker views (${err.message.split("\n")[0]})`);
  }

  const groups = [
    { role: "public", tokens: null, views: publicViews },
    { role: "admin", tokens: adminTokens, views: [...adminViews(houseCode), ...onboardingViews] },
    { role: "worker", tokens: workerTokens, views: workerViews() },
  ].filter((g) => (ROLES.includes("all") || ROLES.includes(g.role)) && (g.role !== "worker" || g.tokens));

  const browser = await launch();
  const report = { base: BASE, api: API, houseCode, ranAt: new Date().toISOString(), widths: {} };

  try {
    for (const width of WIDTHS) {
      const rows = [];
      await browser.setViewport(width, 812, { mobile: width < 900 });
      console.log(`\n=== ${width}px ===`);

      for (const group of groups) {
        await browser.onNewDocument(seedScript(group.tokens));
        for (const view of group.views) {
          if (ONLY.length && !ONLY.includes(view.key)) continue;
          await browser.goto(`${BASE}${view.path}`);
          const measured = await browser.eval(PROBE);
          const landed = await browser.eval("return location.pathname + location.hash;");
          const row = { ...view, role: group.role, landed, ...measured };
          rows.push(row);

          if (SHOTS) {
            const png = await browser.screenshot();
            writeFileSync(join(OUT, "shots", `${width}-${group.role}-${view.key}.png`), png);
          }

          const c = measured.counts;
          const bad = measured.pageOverflow > 0 || c.clipped || c.hiddenColumns;
          console.log(
            `${bad ? "!" : " "} ${view.label.padEnd(34)} overflow=${String(measured.pageOverflow).padStart(3)} ` +
              `clipped=${c.clipped} colsHidden=${c.hiddenColumns} noAffordance=${c.hiddenScroll} ` +
              `tap<44=${c.smallTargets} menu=${measured.nav.toggleFound ? (measured.nav.toggleRendered ? "visible" : "hidden") : "absent"}`,
          );
        }
      }
      report.widths[width] = rows;
      writeFileSync(join(OUT, `audit-${width}.json`), JSON.stringify(rows, null, 2));
    }
  } finally {
    await browser.close();
  }

  writeFileSync(join(OUT, "audit.json"), JSON.stringify(report, null, 2));
  console.log(`\nWrote ${OUT}/audit.json${SHOTS ? ` and ${Object.values(report.widths).flat().length} screenshots` : ""}`);
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
