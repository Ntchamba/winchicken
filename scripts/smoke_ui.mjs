// Pre-deployment smoke test, browser half — part of scripts/smoke.sh.
//
// The API half (smoke_api.py) proves the critical path works; this proves a person can actually
// reach it: the SPA boots, the real login form logs in, and the dashboard renders the farm's
// active batch — with no uncaught JS exception or failed API call on the way. Driven over the
// Chrome DevTools Protocol against a running frontend; nothing is written to the farm.
//
// Args:  node smoke_ui.mjs <cdpWebSocketUrl> <uiBaseUrl> <apiBaseUrl>
// Env:   SMOKE_ADMIN_EMAIL / SMOKE_ADMIN_PASSWORD (default paul@c3.test / Campagne3-Admin2!)
// Exit:  0 = every step passed; 1 = a step failed.

const [, , WS, UI, API] = process.argv;
const EMAIL = process.env.SMOKE_ADMIN_EMAIL || "paul@c3.test";
const PASSWORD = process.env.SMOKE_ADMIN_PASSWORD || "Campagne3-Admin2!";

const ws = new WebSocket(WS);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
let id = 0; const pending = new Map(); const events = [];
ws.onmessage = (m) => {
  const d = JSON.parse(m.data);
  if (d.id && pending.has(d.id)) { const p = pending.get(d.id); pending.delete(d.id); d.error ? p.j(new Error(JSON.stringify(d.error))) : p.r(d.result); }
  else if (d.method) events.push(d);
};
const send = (method, params = {}, sessionId) => new Promise((r, j) => { const i = ++id; pending.set(i, { r, j }); ws.send(JSON.stringify(sessionId ? { id: i, method, params, sessionId } : { id: i, method, params })); });

const { targetId } = await send("Target.createTarget", { url: "about:blank" });
const { sessionId } = await send("Target.attachToTarget", { targetId, flatten: true });
const s = (m, p) => send(m, p, sessionId);
await s("Page.enable"); await s("Runtime.enable"); await s("Network.enable");
await s("Emulation.setDeviceMetricsOverride", { width: 390, height: 780, deviceScaleFactor: 1, mobile: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function evalp(expr) {
  const r = await s("Runtime.evaluate", { expression: `(async () => { ${expr} })()`, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result.value;
}
async function waitFor(expr, label, ms = 15000) {
  const t = Date.now();
  while (Date.now() - t < ms) { try { if (await evalp(`return !!(${expr})`)) return; } catch { /* navigating */ } await sleep(200); }
  throw new Error("timeout waiting for " + label);
}

const steps = [];
let stop = false;
async function step(name, fn) {
  if (stop) return;
  const t0 = Date.now();
  try { steps.push([true, name, (await fn()) || "", Date.now() - t0]); }
  catch (e) { steps.push([false, name, e.message, Date.now() - t0]); stop = true; }
}

// What the smoke must find on the dashboard: the farm's active batch names, read from the API.
const tokenResp = await fetch(API + "/api/auth/login/", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: EMAIL, password: PASSWORD }) });
const apiTok = tokenResp.ok ? (await tokenResp.json()).access : null;
const active = apiTok ? await (await fetch(API + "/api/batches/?status=ACTIVE", { headers: { Authorization: "Bearer " + apiTok } })).json() : { results: [] };

await step("SPA boots (login page renders)", async () => {
  await s("Page.navigate", { url: UI + "/login" });
  await waitFor(`document.querySelector('input[type=email]') && document.querySelector('input[type=password]')`, "login form");
  return "login form rendered";
});

await step("login through the real form", async () => {
  await evalp(`
    const set = (el, v) => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); };
    set(document.querySelector('input[type=email]'), ${JSON.stringify(EMAIL)});
    set(document.querySelector('input[type=password]'), ${JSON.stringify(PASSWORD)});
    document.querySelector('form button[type=submit]').click();
  `);
  // Success = tokens persisted. The 8 s transition screen after it is cosmetic; skip it.
  await waitFor(`localStorage.getItem('winchicken_tokens') || document.querySelector('.auth-card [role=alert], .auth-card .field-error, .auth-card .error')`, "login outcome");
  const ok = await evalp(`return !!localStorage.getItem('winchicken_tokens')`);
  if (!ok) throw new Error("login form showed an error: " + (await evalp(`return document.querySelector('.auth-card').innerText.slice(0, 200)`)));
  return `${EMAIL} logged in`;
});

await step("dashboard loads and shows an active batch", async () => {
  events.length = 0;
  await s("Page.navigate", { url: UI + "/dashboard" });
  await waitFor(`document.querySelectorAll('.sidebar-link').length > 0 || document.querySelector('.dashboard-shell, main')`, "dashboard shell");
  const names = (active.results || []).map((b) => b.name);
  if (!names.length) throw new Error("the farm has no active batch to look for");
  await waitFor(`${JSON.stringify(names)}.some((n) => document.body.innerText.includes(n))`, `an active batch name (${names.join(", ")})`, 15000);
  await sleep(800); // let the remaining mount-time requests settle
  const found = await evalp(`return ${JSON.stringify(names)}.filter((n) => document.body.innerText.includes(n))`);
  return `visible: ${found.join(", ")}`;
});

await step("no JS exception or failed API call", async () => {
  const exc = events.filter((e) => e.method === "Runtime.exceptionThrown").map((e) => e.params.exceptionDetails.exception?.description || e.params.exceptionDetails.text);
  const bad = events.filter((e) => e.method === "Network.responseReceived" && e.params.response.url.includes("/api/") && e.params.response.status >= 400)
    .map((e) => `${e.params.response.status} ${e.params.response.url.replace(API, "")}`);
  if (exc.length || bad.length) throw new Error([...exc, ...bad].slice(0, 5).join(" | "));
  const calls = events.filter((e) => e.method === "Network.responseReceived" && e.params.response.url.includes("/api/")).length;
  return `${calls} API calls, all < 400`;
});

const width = Math.max(...steps.map((x) => x[1].length));
console.log("== Smoke: browser ==");
for (const [ok, name, detail, ms] of steps) console.log(`  [${ok ? "PASS" : "FAIL"}] ${name.padEnd(width)} ${(ms / 1000).toFixed(2).padStart(5)}s  ${detail}`);
const ok = steps.length === 4 && steps.every((x) => x[0]);
console.log(`== ${ok ? "SMOKE OK" : "SMOKE FAILED"} (${UI}) ==`);
ws.close();
process.exit(ok ? 0 : 1);
