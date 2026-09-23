import { useEffect, useState } from "react";
import { WifiOff } from "lucide-react";
import { farmApi } from "../api/endpoints";
import { useIsConnected } from "../pwa/connectivity";
import "./connection-banner.css";

const PROBE_MS = 15000;

/**
 * "Connexion perdue" banner at the top of every dashboard page. The app is left open all day
 * on one screen, so a dropped connection almost always happens inside an already-loaded page,
 * where the service worker's offline screen never shows. Says plainly that nothing can be
 * recorded — there is no offline queue on purpose (money and stock) — and that the figures on
 * screen may be out of date.
 *
 * While shown it asks the server (the public, read-only farm-exists call) every 15 s; the
 * API client's interceptor clears it on the first answer, so it goes away on its own.
 */
export default function ConnectionBanner() {
  const connected = useIsConnected();
  const [checking, setChecking] = useState(false);

  const probe = () => {
    setChecking(true);
    farmApi.exists().catch(() => {}).finally(() => setChecking(false));
  };

  useEffect(() => {
    if (connected) return undefined;
    const id = setInterval(() => farmApi.exists().catch(() => {}), PROBE_MS);
    return () => clearInterval(id);
  }, [connected]);

  if (connected) return null;
  return (
    <div className="connection-banner" role="status" aria-live="polite">
      <WifiOff size={18} strokeWidth={2} aria-hidden="true" />
      <p>
        <strong>Connexion perdue.</strong> Rien ne peut être enregistré pour le moment ; les chiffres affichés peuvent ne plus être à jour.
      </p>
      <button type="button" onClick={probe} disabled={checking}>
        {checking ? "Vérification…" : "Réessayer"}
      </button>
    </div>
  );
}
