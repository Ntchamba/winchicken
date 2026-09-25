import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import "./app-loading-screen.css";

const SLOW_AFTER_MS = 6000;

/**
 * What the app shows before it knows who is logged in (ProtectedRoute). It used to be a bare
 * "Chargement…" with nothing to tap for as long as the server took; after a few seconds — or at
 * once when the server could not be reached — it now says so in plain words and offers the two
 * things a user can actually do: try again, or log out.
 *
 * @param {boolean} [unreachable] - The server did not answer: show the explanation now.
 * @param {() => void} onRetry
 * @param {() => void} onLogout
 */
export default function AppLoadingScreen({ unreachable = false, onRetry, onLogout }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), SLOW_AFTER_MS);
    return () => clearTimeout(timer);
  }, []);
  const explain = unreachable || slow;

  return (
    <div className="app-loading" role="status" aria-live="polite">
      <img src="/logo-mark.png" alt="" aria-hidden="true" className="app-loading-logo" />
      <p className="app-loading-title">WINCHICKEN</p>
      {!unreachable && (
        <p className="app-loading-text">
          <Loader2 size={18} className="spin" aria-hidden="true" /> Chargement…
        </p>
      )}
      {explain && (
        <>
          <p className="app-loading-text">
            {unreachable
              ? "Le serveur de la ferme ne répond pas. Vérifiez que le téléphone est bien connecté au réseau de la ferme, puis réessayez."
              : "Le serveur met du temps à répondre. Vous pouvez patienter ou réessayer."}
          </p>
          <div className="app-loading-actions">
            <button type="button" className="save-button" onClick={onRetry}>Réessayer</button>
            <button type="button" className="add-button" onClick={onLogout}>Se déconnecter</button>
          </div>
        </>
      )}
    </div>
  );
}
