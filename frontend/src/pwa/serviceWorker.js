/**
 * The one registration of /sw.js (Web Push + installable-app shell). Called on every load from
 * main.jsx so the app is installable and gets its offline page for everyone, not only for users
 * who turned on notifications; useWebPush awaits the same promise instead of registering again.
 *
 * Memoised: registering twice is harmless to the browser but two call sites are how this
 * codebase has drifted before.
 */
let registration = null;

export const serviceWorkerSupported = () => typeof navigator !== "undefined" && "serviceWorker" in navigator;

export function registerServiceWorker() {
  if (!serviceWorkerSupported()) return Promise.reject(new Error("Service worker non pris en charge"));
  if (!registration) {
    registration = navigator.serviceWorker.register("/sw.js");
    // A failed registration must not stay cached as a rejected promise forever.
    registration.catch(() => { registration = null; });
  }
  return registration;
}
