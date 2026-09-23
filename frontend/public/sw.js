/* Winchicken service worker — desktop notifications (Web Push) and, since 2026-09-24, the
   installable-app shell: an offline page and a cache of the files that never change.
   Registered on every load by src/pwa/serviceWorker.js (useWebPush reuses that registration).
   Kept dependency-free and tiny. */

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: "Winchicken", body: event.data && event.data.text() };
  }
  const title = data.title || "Winchicken";
  const options = {
    body: data.body || "",
    tag: data.tag || undefined,
    renotify: Boolean(data.tag),
    icon: "/favicon-32x32.png",
    badge: "/favicon-16x16.png",
    data: { url: data.url || "/" },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ("focus" in client) {
          client.focus();
          if ("navigate" in client && target !== "/") client.navigate(target);
          return undefined;
        }
      }
      return self.clients.openWindow(target);
    }),
  );
});

/* --- App shell (2026-09-24) -------------------------------------------------------------
   Deliberately NOT an offline-first app: Winchicken records money and stock, and entries
   queued offline could later conflict with the server. So:
   - API calls and every non-GET request are never touched — no cached data, no queued writes.
   - A page load always goes to the network; only when that fails is the French offline page
     served in its place (it reloads itself once the connection is back).
   - Cache-first only for files whose URL changes when their content does: built /assets/*,
     Vite's pre-bundled dependencies (?v=<hash>), the icons and Google Fonts. App source
     modules are left to the network, so a code change can never be served stale — this
     project has lost time before to fixes that did not show up. */
const SHELL_CACHE = "winchicken-shell-v1";
const OFFLINE_URL = "/offline.html";
const PRECACHE = [OFFLINE_URL, "/icons/icon-192.png", "/manifest.webmanifest"];
const FONT_ORIGINS = ["https://fonts.googleapis.com", "https://fonts.gstatic.com"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL_CACHE).then((cache) => cache.addAll(PRECACHE)));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((key) => key.startsWith("winchicken-shell-") && key !== SHELL_CACHE).map((key) => caches.delete(key)),
    )),
  );
});

function isImmutable(url) {
  if (FONT_ORIGINS.includes(url.origin)) return true;
  if (url.origin !== self.location.origin) return false;
  return url.pathname.startsWith("/assets/")
    || url.pathname.startsWith("/icons/")
    || (url.pathname.startsWith("/node_modules/.vite/deps/") && url.searchParams.has("v"));
}

async function cacheFirst(request) {
  const cache = await caches.open(SHELL_CACHE);
  const hit = await cache.match(request);
  if (hit) return hit;
  const response = await fetch(request);
  // Opaque (cross-origin no-cors) responses are cached too: Google's font files are served
  // that way to a stylesheet, and they are immutable by URL.
  if (response.ok || response.type === "opaque") cache.put(request, response.clone());
  return response;
}

// The precache only reruns when this file changes; refreshing the offline page after each
// successful page load keeps an edited offline.html from staying stale in the cache.
function refreshOfflinePage() {
  return caches.open(SHELL_CACHE).then((cache) => cache.add(new Request(OFFLINE_URL, { cache: "no-store" }))).catch(() => {});
}

async function pageOrOffline(request, event) {
  try {
    // no-store: offline, Chrome would otherwise answer from its HTTP cache with a stale
    // index.html whose scripts then fail — a blank page, the one outcome this must prevent.
    const response = await fetch(request.url, { cache: "no-store", credentials: "same-origin" });
    event.waitUntil(refreshOfflinePage());
    return response;
  } catch {
    const cache = await caches.open(SHELL_CACHE);
    return (await cache.match(OFFLINE_URL)) || Response.error();
  }
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin === self.location.origin && url.pathname.startsWith("/api/")) return;

  if (request.mode === "navigate" && url.origin === self.location.origin) {
    event.respondWith(pageOrOffline(request, event));
    return;
  }
  if (isImmutable(url)) event.respondWith(cacheFirst(request));
});
