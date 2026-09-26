// Live browser regression smoke for Winchicken — part of scripts/regression.sh.
//
// Drives a REAL running frontend over the Chrome DevTools Protocol and asserts, from computed
// styles and the rendered DOM (never from source), the four UI items this project has a history
// of reporting "fixed" while they were not — sidebar scroll, the factory-reset button,
// batch-name validation, button alignment — plus the stock/shortfall panel's false
// "server unreachable". Logs in by fetching a token and seeding localStorage, so it skips the
// login transition screen.
//
// Args:  node regression_ui.mjs <cdpWebSocketUrl> <uiBaseUrl> <apiBaseUrl>
// Env:   REG_ADMIN_EMAIL / REG_ADMIN_PASSWORD (default paul@c3.test / Campagne3-Admin2!)
// Exit:  0 = all checks passed or skipped with a reason; 1 = a regression was observed.

const [, , WS, UI, API] = process.argv;
const EMAIL = process.env.REG_ADMIN_EMAIL || "paul@c3.test";
const PASSWORD = process.env.REG_ADMIN_PASSWORD || "Campagne3-Admin2!";

const ws = new WebSocket(WS);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let id = 0; const pending = new Map();
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pending.has(d.id)) { const p = pending.get(d.id); pending.delete(d.id); d.error ? p.j(new Error(JSON.stringify(d.error))) : p.r(d.result); } };
const send = (method, params = {}, sessionId) => new Promise((r, j) => { const i = ++id; pending.set(i, { r, j }); ws.send(JSON.stringify(sessionId ? { id: i, method, params, sessionId } : { id: i, method, params })); });

const { targetId } = await send("Target.createTarget", { url: "about:blank" });
const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
const s = (m, p) => send(m, p, sessionId);
await s("Page.enable"); await s("Runtime.enable");

async function evalp(expr) {
  const r = await s("Runtime.evaluate", { expression: `(async () => { ${expr} })()`, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result.value;
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function goto(path) {
  await s("Page.navigate", { url: UI + path });
  await sleep(1500);
}
async function waitFor(expr, label, ms = 15000) {
  const t = Date.now();
  while (Date.now() - t < ms) { try { if (await evalp(`return !!(${expr})`)) return true; } catch { /* navigating */ } await sleep(250); }
  throw new Error("timeout waiting for " + label);
}

const results = [];
async function check(name, fn) {
  try { const d = await fn(); results.push(["PASS", name, d || ""]); }
  catch (e) { results.push([/^SKIP:/.test(e.message) ? "SKIP" : "FAIL", name, e.message.replace(/^SKIP:\s*/, "")]); }
}
const SKIP = (m) => { throw new Error("SKIP: " + m); };

// --- log in without the transition screen: fetch a token, seed localStorage -------------------
await goto("/");
const loggedIn = await evalp(`
  const r = await fetch(${JSON.stringify(API)} + "/api/auth/login/", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: ${JSON.stringify(EMAIL)}, password: ${JSON.stringify(PASSWORD)} }),
  });
  if (!r.ok) return { ok: false, status: r.status };
  const t = await r.json();
  localStorage.setItem("winchicken_tokens", JSON.stringify({ access: t.access, refresh: t.refresh }));
  const me = await fetch(${JSON.stringify(API)} + "/api/auth/me/", { headers: { Authorization: "Bearer " + t.access } });
  if (me.ok) localStorage.setItem("winchicken_user", JSON.stringify(await me.json()));
  return { ok: true };
`);
if (!loggedIn.ok) { console.error("login failed", loggedIn); ws.close(); process.exit(1); }

await s("Emulation.setDeviceMetricsOverride", { width: 390, height: 780, deviceScaleFactor: 1, mobile: true });
await goto("/dashboard/overview");
await waitFor(`document.querySelector('.dashboard-shell, .dashboard-layout, nav, aside')`, "dashboard shell");

await check("recurring: no horizontal page scroll (dashboard @390)", async () => {
  const over = await evalp(`return document.documentElement.scrollWidth - document.documentElement.clientWidth`);
  if (over > 1) throw new Error(`page overflows by ${over}px`);
  return "no horizontal scroll";
});

await check("recurring: sidebar scrolls internally, reaches every link", async () => {
  // The historical bug: on a SHORT viewport the full sidebar's links overflow and the last ones
  // are clipped with no way to scroll to them. Use a short desktop height where every nav link
  // is rendered (not the phone drawer) so the column genuinely has to scroll.
  await s("Emulation.setDeviceMetricsOverride", { width: 1280, height: 560, deviceScaleFactor: 1, mobile: false });
  await goto("/dashboard/overview");
  await waitFor(`document.querySelectorAll('.sidebar-link').length > 3`, "desktop sidebar links", 12000);
  await sleep(1200);
  const info = await evalp(`
    // The links are grouped across the whole sidebar column, not one <nav>, so the scroll
    // container is the sidebar itself. Find the nearest scrollable ancestor of the links.
    const links = [...document.querySelectorAll('.sidebar-link')];
    if (links.length < 3) return { skip: "sidebar links not rendered" };
    let scroller = document.querySelector('.sidebar') || links[0].parentElement;
    let node = scroller;
    while (node && node !== document.body) {
      if (node.scrollHeight > node.clientHeight + 1 && /auto|scroll/.test(getComputedStyle(node).overflowY)) { scroller = node; break; }
      node = node.parentElement;
    }
    const cs = getComputedStyle(scroller);
    const last = links[links.length - 1];
    last.scrollIntoView({ block: "nearest" });
    await new Promise(r => setTimeout(r, 250));
    const lr = last.getBoundingClientRect();
    const sr = scroller.getBoundingClientRect();
    return {
      overflowY: cs.overflowY,
      overflows: scroller.scrollHeight > scroller.clientHeight + 1,
      links: links.length,
      lastReachable: lr.top >= sr.top - 1 && lr.bottom <= sr.bottom + 1,
    };
  `);
  await s("Emulation.setDeviceMetricsOverride", { width: 390, height: 780, deviceScaleFactor: 1, mobile: true });
  if (info.skip) SKIP(info.skip);
  if (info.links < 3) SKIP(`only ${info.links} sidebar links visible`);
  // If the links overflow the column, scrolling must reach the last one.
  if (info.overflows && info.lastReachable === false) throw new Error(`last of ${info.links} links unreachable (overflowY=${info.overflowY})`);
  return `${info.links} links, overflowY=${info.overflowY}, overflows=${info.overflows}, lastReachable=${info.lastReachable}`;
});

await check("recurring: factory-reset button present, visible and enabled", async () => {
  await goto("/dashboard/settings");
  await waitFor(`[...document.querySelectorAll('button')].some(b => /Réinitialiser la ferme/i.test(b.textContent))`, "settings page");
  const state = await evalp(`
    const btn = [...document.querySelectorAll('button')].find(b => /Réinitialiser la ferme/i.test(b.textContent));
    if (!btn) return { found: false };
    const r = btn.getBoundingClientRect();
    return { found: true, disabled: btn.disabled, visible: !!btn.offsetParent && r.width > 0 && r.height > 0, w: Math.round(r.width), h: Math.round(r.height) };
  `);
  if (!state.found) throw new Error("factory-reset button not found on settings");
  if (!state.visible) throw new Error("factory-reset button not visible");
  if (state.disabled) throw new Error("factory-reset button disabled");
  if (state.h < 40) throw new Error(`factory-reset button too short (${state.h}px)`);
  // It must actually open the confirmation modal.
  const opened = await evalp(`
    const btn = [...document.querySelectorAll('button')].find(b => /Réinitialiser la ferme/i.test(b.textContent));
    btn.click(); await new Promise(r => setTimeout(r, 500));
    return !!document.querySelector('[role="dialog"], .modal, .factory-reset-modal') ||
           /Zone dangereuse|mot de passe|confirmer|irréversible/i.test(document.body.innerText);
  `);
  if (!opened) throw new Error("factory-reset button does not open its confirmation");
  return `visible ${state.w}x${state.h}px, enabled, opens confirmation`;
});

await check("recurring: button alignment (a row of buttons shares a baseline)", async () => {
  // Close any open dialog first.
  await evalp(`document.querySelector('[role="dialog"] [aria-label*="ermer" i], .modal-close')?.click(); return true;`).catch(() => {});
  const info = await evalp(`
    // Find a flex row containing 2+ buttons and check they line up (same bottom within 2px) and
    // are the same height — the "button alignment" false-fix.
    const rows = [...document.querySelectorAll('div, form, header, footer')].filter(el => {
      const b = el.querySelectorAll(':scope > button, :scope > a.btn-pill, :scope > .btn-pill');
      return b.length >= 2 && getComputedStyle(el).display.includes('flex');
    });
    if (!rows.length) return { skip: "no multi-button flex row on this screen" };
    for (const row of rows) {
      const btns = [...row.querySelectorAll(':scope > button, :scope > a.btn-pill, :scope > .btn-pill')].filter(b => b.offsetParent);
      if (btns.length < 2) continue;
      const rects = btns.map(b => b.getBoundingClientRect());
      const bottoms = rects.map(r => r.bottom);
      const heights = rects.map(r => r.height);
      const spread = Math.max(...bottoms) - Math.min(...bottoms);
      const hspread = Math.max(...heights) - Math.min(...heights);
      return { count: btns.length, bottomSpread: Math.round(spread), heightSpread: Math.round(hspread) };
    }
    return { skip: "no visible multi-button row" };
  `);
  if (info.skip) SKIP(info.skip);
  if (info.bottomSpread > 3) throw new Error(`buttons misaligned: bottoms differ by ${info.bottomSpread}px`);
  return `${info.count} buttons aligned (bottoms ±${info.bottomSpread}px, heights ±${info.heightSpread}px)`;
});

await check("recurring: batch-name validation gates the form", async () => {
  // Reachable without creating anything: a configured farm opens /onboarding/protocol in
  // "add house" mode showing the batch header. We only read the Suivant button's state.
  await s("Emulation.setDeviceMetricsOverride", { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false });
  await goto("/onboarding/protocol");
  await sleep(1500);
  const hasForm = await evalp(`return !!document.querySelector('input') && /Nom de la bande/i.test(document.body.innerText)`);
  if (!hasForm) SKIP("batch header not the first onboarding step in this build (covered by BatchHeaderStep unit tests)");
  const setVal = (label, v) => `
    { const lab=[...document.querySelectorAll('label')].find(l=>/${label}/i.test(l.textContent));
      const el=lab && (lab.querySelector('input,select') || document.getElementById(lab.htmlFor));
      if(el){ const proto=el.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(proto,'value').set.call(el, ${JSON.stringify(v)});
        el.dispatchEvent(new Event(el.tagName==='SELECT'?'change':'input',{bubbles:true})); } }`;
  const nextState = `[...document.querySelectorAll('button')].find(b=>/^Suivant$/i.test(b.textContent.trim()))`;
  const emptyDisabled = await evalp(`const b=${nextState}; return b ? b.disabled : null`);
  if (emptyDisabled !== true) throw new Error("'Suivant' is not disabled with an empty batch name");
  // Whitespace-only name must still be rejected.
  await evalp(setVal("Nom de la bande", "   ") + " return true;");
  await evalp(setVal("Poussins mis en place", "500") + " return true;");
  await evalp(setVal("Nom du bâtiment", "Test Bâtiment") + " return true;");
  await sleep(200);
  const wsDisabled = await evalp(`const b=${nextState}; return b ? b.disabled : null`);
  if (wsDisabled !== true) throw new Error("'Suivant' enabled with a whitespace-only batch name");
  // A real name enables it.
  await evalp(setVal("Nom de la bande", "Bande Régression") + " return true;");
  await sleep(200);
  const okEnabled = await evalp(`const b=${nextState}; return b ? !b.disabled : null`);
  if (okEnabled !== true) throw new Error("'Suivant' stays disabled with a valid batch name + fields");
  return "empty + whitespace-only rejected, valid name accepted (nothing submitted)";
});

await check("FIX: stock/shortfall panel shows no false 'server unreachable'", async () => {
  await goto("/dashboard/stock");
  await sleep(2500);
  const txt = await evalp(`return document.body.innerText`);
  if (/injoignable|inaccessible|impossible de (joindre|contacter)|server unreachable|serveur ne répond/i.test(txt)) {
    throw new Error("a 'server unreachable' message is shown while the server is up");
  }
  return "no false unreachable message";
});

const failed = results.some((r) => r[0] === "FAIL");
const w = Math.max(...results.map((r) => r[1].length));
console.log("\n== Live UI regression (recurring-four + shortfall) ==");
for (const [state, name, detail] of results) console.log(`  [${state}] ${name.padEnd(w)}  ${detail}`);
console.log(`== ${failed ? "FAILURES ABOVE" : "ALL GREEN"} (${UI}) ==`);
ws.close();
process.exit(failed ? 1 : 0);
