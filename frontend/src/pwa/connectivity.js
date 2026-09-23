import { useSyncExternalStore } from "react";

/**
 * Whether the app can currently reach the farm server — for the "connexion perdue" banner.
 *
 * Two signals, because either alone misses a real case: the browser's online/offline events
 * (the phone lost its network) and the API client's own outcomes (the phone is on the farm
 * Wi-Fi but the server does not answer — navigator.onLine stays true then). Any response,
 * even an error status, proves the server is reachable; a request with no response at all
 * proves it is not. Nothing here retries or queues a request: while this is false, writes
 * fail and say so, exactly as they would without it.
 */
let serverReachable = true;
const listeners = new Set();
const emit = () => listeners.forEach((listener) => listener());

export function reportServerReachable(reachable) {
  if (reachable === serverReachable) return;
  serverReachable = reachable;
  emit();
}

function subscribe(listener) {
  listeners.add(listener);
  window.addEventListener("online", listener);
  window.addEventListener("offline", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("online", listener);
    window.removeEventListener("offline", listener);
  };
}

const snapshot = () => navigator.onLine && serverReachable;

/** @returns {boolean} true while the network is up and the last request got an answer. */
export function useIsConnected() {
  return useSyncExternalStore(subscribe, snapshot, () => true);
}
