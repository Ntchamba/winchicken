import { useCallback, useEffect, useState } from "react";
import { pushApi } from "../api/endpoints";

/**
 * Desktop notifications via the Web Push API (2026-08-31). Registers `/sw.js`, subscribes the
 * browser's push endpoint with the server's VAPID key, and posts it to
 * /api/push-subscriptions/. Once granted, notifications fire even with every Winchicken tab
 * closed — the OS/browser wakes the service worker.
 *
 * Returns:
 *   supported   — the browser has SW + Push + Notification
 *   enabled     — the server has VAPID keys configured
 *   permission  — "default" | "granted" | "denied"
 *   subscribed  — a push subscription currently exists
 *   busy        — a subscribe/unsubscribe call is in flight
 *   error       — last failure message, if any
 *   enable()    — request permission + subscribe
 *   disable()   — unsubscribe (this browser only)
 */
const SUPPORTED =
  typeof window !== "undefined" &&
  "serviceWorker" in navigator &&
  "PushManager" in window &&
  "Notification" in window;

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  const output = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) output[i] = raw.charCodeAt(i);
  return output;
}

async function getRegistration() {
  return navigator.serviceWorker.register("/sw.js");
}

export default function useWebPush() {
  const [enabled, setEnabled] = useState(false);
  const [permission, setPermission] = useState(SUPPORTED ? Notification.permission : "denied");
  const [subscribed, setSubscribed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!SUPPORTED) return;
    let cancelled = false;
    (async () => {
      try {
        const { data } = await pushApi.publicKey();
        if (cancelled) return;
        setEnabled(Boolean(data.enabled && data.publicKey));
        const reg = await getRegistration();
        const sub = await reg.pushManager.getSubscription();
        if (!cancelled) setSubscribed(Boolean(sub));
      } catch {
        /* server unreachable / SW blocked — leave defaults */
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const enable = useCallback(async () => {
    if (!SUPPORTED) { setError("Ce navigateur ne gère pas les notifications."); return; }
    setBusy(true);
    setError("");
    try {
      const perm = await Notification.requestPermission();
      setPermission(perm);
      if (perm !== "granted") { setError("Autorisation refusée."); return; }

      const { data } = await pushApi.publicKey();
      if (!data.enabled || !data.publicKey) { setError("Le serveur n'est pas configuré pour le push."); return; }

      const reg = await getRegistration();
      let sub = await reg.pushManager.getSubscription();
      if (!sub) {
        sub = await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(data.publicKey),
        });
      }
      await pushApi.subscribe(sub.toJSON());
      setSubscribed(true);
    } catch (e) {
      setError(e?.message || "Impossible d'activer les notifications.");
    } finally {
      setBusy(false);
    }
  }, []);

  const disable = useCallback(async () => {
    if (!SUPPORTED) return;
    setBusy(true);
    setError("");
    try {
      const reg = await getRegistration();
      const sub = await reg.pushManager.getSubscription();
      if (sub) {
        await pushApi.unsubscribe(sub.endpoint).catch(() => {});
        await sub.unsubscribe();
      }
      setSubscribed(false);
    } catch (e) {
      setError(e?.message || "Impossible de désactiver les notifications.");
    } finally {
      setBusy(false);
    }
  }, []);

  return { supported: SUPPORTED, enabled, permission, subscribed, busy, error, enable, disable };
}
