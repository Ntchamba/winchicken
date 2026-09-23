import { useSyncExternalStore } from "react";

/**
 * "Installer l'application" support. Imported for its side effect from main.jsx so the
 * browser's one-shot `beforeinstallprompt` event is caught at startup — it usually fires long
 * before anyone opens Paramètres, where the button lives.
 *
 * preventDefault() on that event also stops Chrome's automatic install mini-bar: the only
 * prompt is the button the user presses, never a popup.
 */
let deferredPrompt = null;
let installedThisSession = false;
const listeners = new Set();
const emit = () => listeners.forEach((listener) => listener());

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredPrompt = event;
    emit();
  });
  window.addEventListener("appinstalled", () => {
    deferredPrompt = null;
    installedThisSession = true;
    emit();
  });
}

const runningInstalled = () =>
  window.matchMedia?.("(display-mode: standalone)")?.matches || window.navigator.standalone === true;

const isIOS = () => /iphone|ipad|ipod/i.test(window.navigator.userAgent);

let cached = null;
function snapshot() {
  const next = {
    installed: installedThisSession || runningInstalled(),
    canInstall: deferredPrompt !== null,
    ios: isIOS(),
  };
  if (!cached || cached.installed !== next.installed || cached.canInstall !== next.canInstall || cached.ios !== next.ios) cached = next;
  return cached;
}

function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Opens the browser's own install dialog. Resolves to "accepted" | "dismissed" | "unavailable". */
export async function promptInstall() {
  if (!deferredPrompt) return "unavailable";
  const event = deferredPrompt;
  // The event can be used once; Chrome fires a fresh one later if the user dismissed it.
  deferredPrompt = null;
  emit();
  event.prompt();
  const { outcome } = await event.userChoice;
  return outcome;
}

/** @returns {{installed: boolean, canInstall: boolean, ios: boolean}} */
export function useInstallState() {
  return useSyncExternalStore(subscribe, snapshot, () => ({ installed: false, canInstall: false, ios: false }));
}
