/**
 * Minimal Chrome DevTools Protocol driver.
 *
 * Why hand-rolled rather than puppeteer: Node 24 ships a global `WebSocket`, so driving a real
 * Chrome needs no package at all. Adding a browser-automation dependency to a farm laptop that
 * deploys offline is a cost this repo deliberately does not pay — see docs/deviations.md.
 */
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const CHROME = process.env.CHROME_BIN || "google-chrome-stable";

/** Poll an HTTP endpoint until it answers, so we never race Chrome's startup. */
async function waitFor(url, timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    try {
      const res = await fetch(url);
      if (res.ok) return await res.json();
    } catch {
      /* not up yet */
    }
    if (Date.now() > deadline) throw new Error(`timed out waiting for ${url}`);
    await new Promise((r) => setTimeout(r, 120));
  }
}

/**
 * Launch a headless Chrome and return a driver bound to one fresh tab.
 *
 * `tz` is passed through the environment rather than via Emulation.setTimezoneOverride so the
 * browser process itself runs on farm-local time: Date, Intl and toLocaleDateString all behave
 * exactly as they do in Douala, which is what every date-defaulting component reads.
 */
export async function launch({ port = 9333, tz = "Africa/Douala" } = {}) {
  const profile = mkdtempSync(join(tmpdir(), "winchicken-audit-"));
  const chrome = spawn(
    CHROME,
    [
      "--headless=new",
      "--disable-gpu",
      "--no-sandbox",
      "--no-first-run",
      "--disable-dev-shm-usage",
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${profile}`,
      "about:blank",
    ],
    { stdio: "ignore", detached: true, env: { ...process.env, TZ: tz } },
  );
  chrome.unref();

  const version = await waitFor(`http://127.0.0.1:${port}/json/version`);
  const ws = new WebSocket(version.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", reject, { once: true });
  });

  let nextId = 0;
  const pending = new Map();
  ws.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data);
    const slot = pending.get(msg.id);
    if (!slot) return;
    pending.delete(msg.id);
    if (msg.error) slot.reject(new Error(`${msg.error.message} (${JSON.stringify(slot.params)})`));
    else slot.resolve(msg.result);
  });

  const call = (method, params = {}, sessionId) =>
    new Promise((resolve, reject) => {
      const id = ++nextId;
      pending.set(id, { resolve, reject, params });
      ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
    });

  const { targetId } = await call("Target.createTarget", { url: "about:blank" });
  const { sessionId } = await call("Target.attachToTarget", { targetId, flatten: true });
  const send = (method, params) => call(method, params, sessionId);

  await send("Page.enable");
  await send("Runtime.enable");

  return {
    send,
    /** Run an expression in the page and return its value. Wrapped in an IIFE: every
        Runtime.evaluate shares one global scope, so bare `const` collides across calls. */
    async eval(expression) {
      const { result, exceptionDetails } = await send("Runtime.evaluate", {
        expression: `(() => { ${expression} })()`,
        returnByValue: true,
        awaitPromise: true,
      });
      if (exceptionDetails) throw new Error(exceptionDetails.exception?.description || "eval failed");
      return result.value;
    },
    /** Install a script that runs before any app JS on every navigation. */
    onNewDocument(source) {
      return send("Page.addScriptToEvaluateOnNewDocument", { source });
    },
    async setViewport(width, height, { mobile = true } = {}) {
      await send("Emulation.setDeviceMetricsOverride", {
        width,
        height,
        deviceScaleFactor: 1,
        mobile,
        screenWidth: width,
        screenHeight: height,
      });
      // maxTouchPoints must be 1..16 even when disabling — passing 0 is rejected outright and
      // takes the whole desktop-width pass down with it.
      await send("Emulation.setTouchEmulationEnabled", { enabled: mobile, maxTouchPoints: mobile ? 5 : 1 });
    },
    /**
     * Navigate and wait for the load event.
     *
     * Always goes via about:blank first. Two reasons, both learned the hard way: a URL that
     * differs from the current one only by its #fragment does not reload, so Page.loadEventFired
     * never arrives and the run hangs forever on the second /dashboard/finances#... view; and
     * measuring every view from a fresh mount is what makes two views comparable. The load wait
     * is bounded as well, so a page that never fires load costs one view, not the whole run.
     */
    async goto(url, { settleMs = 900, timeoutMs = 20000 } = {}) {
      const waitForLoad = () =>
        new Promise((resolve) => {
          const timer = setTimeout(finish, timeoutMs);
          function finish() {
            clearTimeout(timer);
            ws.removeEventListener("message", onMessage);
            resolve();
          }
          function onMessage(event) {
            const msg = JSON.parse(event.data);
            if (msg.sessionId === sessionId && msg.method === "Page.loadEventFired") finish();
          }
          ws.addEventListener("message", onMessage);
        });

      const blank = waitForLoad();
      await send("Page.navigate", { url: "about:blank" });
      await blank;

      const loaded = waitForLoad();
      await send("Page.navigate", { url });
      await loaded;
      // The app fetches on mount everywhere; settle before measuring or every box reads 0.
      await new Promise((r) => setTimeout(r, settleMs));
    },
    async screenshot({ fullPage = true } = {}) {
      const { data } = await send("Page.captureScreenshot", {
        format: "png",
        captureBeyondViewport: fullPage,
      });
      return Buffer.from(data, "base64");
    },
    async close() {
      try {
        ws.close();
        process.kill(-chrome.pid, "SIGTERM");
      } catch {
        /* already gone */
      }
      // Chrome keeps writing its profile for a moment after SIGTERM, so a straight rmSync
      // races it and throws ENOTEMPTY. Retry briefly, then leave it to the OS temp sweep
      // rather than failing a run that already produced its results.
      for (let attempt = 0; attempt < 10; attempt += 1) {
        try {
          rmSync(profile, { recursive: true, force: true });
          return;
        } catch {
          await new Promise((r) => setTimeout(r, 150));
        }
      }
    },
  };
}
