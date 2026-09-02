import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Loader2, X } from "lucide-react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { farmApi } from "../api/endpoints";
import { getServerErrorMessage } from "../api/errors";
import { useAuth } from "../context/AuthContext";
import "../styles/protocol-edit-modal.css";

const EASE_EXPO = [0.16, 1, 0.3, 1];
const FOCUSABLE = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

// Grouped, plain-French breakdown of exactly what apps.core.services.factory_reset_farm wipes
// (docs/deviations.md Part 12) — every table reachable by CASCADE from Farm. Kept as a static
// list here rather than fetched from the backend: it names model categories, not live data, and
// changing what gets wiped is a backend code change anyway (this list should move in lockstep
// with that function's own docstring, not with a database query).
const WIPED_CATEGORIES = [
  "Tous les bâtiments et toutes les bandes, avec leur historique quotidien (mortalité, œufs, pesées) et leurs rapports de clôture",
  "Tout le stock : articles, mouvements de stock et vaccinations",
  "Toutes les pannes d'équipement et tous les cas inhabituels signalés",
  "Toutes les données financières : dépenses, ventes et commandes fournisseurs",
  "Toutes les règles d'alerte, alertes, SMS envoyés et préférences de notification",
  "Tous les protocoles (catégories et lignes) de chaque bâtiment",
  "Tous les comptes utilisateurs de la ferme, y compris le vôtre",
];

/**
 * Multi-step confirmation for POST /api/farm/reset/ (2026-08-26) — the sanctioned exception to
 * this project's "no way to delete a farm" rule (docs/deviations.md Part 12). Two screens
 * rather than four separate clicks (the task's steps 1–4 collapse naturally into "read the
 * consequences" then "prove it's really you, twice"): an explanation screen naming every wiped
 * category, then a second screen requiring both the exact `Farm.name` typed back and the
 * caller's current password before "Réinitialiser la ferme" is enabled at all — the password's
 * *correctness* can only be checked server-side (there is nothing to compare it against on the
 * frontend), so a wrong password still reaches the server and comes back as a rejected request
 * with an inline error, not a disabled button.
 *
 * Chrome (backdrop/panel/close button, focus trap, Escape-to-close) reuses
 * `protocol-edit-modal.css`'s classes exactly as `ProtocolEditModal` does — no dirty-tracking
 * needed here, this form has nothing worth warning about losing on close.
 *
 * `mode="pre-login"` (used from `/login`, where there is no session): prepends a step-0
 * "administrator credentials" screen that calls `POST /api/farm/reset/request/` and, on
 * success, carries a short-lived server token into the same explain → confirm screens. The
 * confirm screen then only asks for the farm name (the password was already proven in step 0)
 * and the final action calls `POST /api/farm/reset/confirm/` instead of the session endpoint.
 *
 * @param {boolean} open
 * @param {() => void} onClose
 * @param {"dashboard" | "pre-login"} [mode="dashboard"]
 */
export default function FactoryResetModal({ open, onClose, mode = "dashboard" }) {
  const isPreLogin = mode === "pre-login";
  const { user, logout } = useAuth();
  const reduceMotion = useReducedMotion();
  const panelRef = useRef(null);
  const triggerRef = useRef(null);

  const [step, setStep] = useState(isPreLogin ? "credentials" : "explain");
  const [email, setEmail] = useState("");
  const [farmNameInput, setFarmNameInput] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  // pre-login only: filled by the step-0 credential check, consumed by the confirm step.
  const [resetToken, setResetToken] = useState("");
  const [verifiedFarmName, setVerifiedFarmName] = useState("");

  // dashboard mode reads the farm name from the live session; pre-login mode only learns it
  // from the server once credentials check out in step 0.
  const farmName = isPreLogin ? verifiedFarmName : user?.farm_name;

  useEffect(() => {
    if (!open) return;
    setStep(isPreLogin ? "credentials" : "explain");
    setEmail("");
    setFarmNameInput("");
    setPassword("");
    setResetToken("");
    setVerifiedFarmName("");
    setError("");
    setSubmitting(false);
    triggerRef.current = document.activeElement;
  }, [open, isPreLogin]);

  const requestClose = () => {
    if (submitting) return;
    onClose();
    triggerRef.current?.focus?.();
  };

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e) => {
      if (e.key === "Escape") {
        requestClose();
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;
      const focusable = panelRef.current.querySelectorAll(FOCUSABLE);
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    document.body.style.overflow = "hidden";
    const raf = requestAnimationFrame(() => panelRef.current?.focus());
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = "";
      cancelAnimationFrame(raf);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, step]);

  const nameMatches = farmNameInput === farmName;
  // Shown inline under the field as soon as the user has typed something that doesn't match —
  // no more "the button does nothing and never says why".
  const nameMismatch = farmNameInput.trim().length > 0 && !nameMatches;

  const handleVerifyCredentials = async () => {
    if (!email || !password || submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const { data } = await farmApi.resetRequest(email, password);
      setResetToken(data.token);
      setVerifiedFarmName(data.farm_name);
      setPassword(""); // proven now; the confirm step is authorised by the token, not the password
      setStep("explain");
    } catch (err) {
      setError(getServerErrorMessage(err, "Identifiants invalides."));
    } finally {
      setSubmitting(false);
    }
  };

  const handleConfirm = async () => {
    if (submitting) return;
    // Clicking must always produce feedback — either it proceeds, or it says exactly what to fix.
    if (!farmNameInput.trim()) {
      setError("Saisissez le nom de la ferme pour confirmer.");
      return;
    }
    if (!nameMatches) {
      setError(`Le nom saisi ne correspond pas au nom exact de la ferme : « ${farmName} ».`);
      return;
    }
    if (!isPreLogin && password.length === 0) {
      setError("Saisissez votre mot de passe pour confirmer.");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      if (isPreLogin) {
        await farmApi.resetConfirm(resetToken, farmNameInput);
      } else {
        await farmApi.reset(password);
        // The admin's own account no longer exists server-side the instant the request above
        // resolved — logout()/redirect here is just clearing the now-stale local copy of that
        // fact, not the thing that actually ends the session.
        logout();
      }
      window.location.href = "/";
    } catch (err) {
      setError(
        isPreLogin
          ? getServerErrorMessage(err, "La réinitialisation a échoué. Recommencez depuis la connexion.")
          : err.response?.data?.password?.[0] || err.response?.data?.detail || "Mot de passe incorrect.",
      );
      setSubmitting(false);
    }
  };

  const backdropTransition = { duration: reduceMotion ? 0 : 0.3, ease: EASE_EXPO };
  const panelTransition = { duration: reduceMotion ? 0 : 0.35, ease: EASE_EXPO };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="protocol-modal-backdrop"
          initial={{ opacity: 0, backdropFilter: "blur(0px)" }}
          animate={{ opacity: 1, backdropFilter: "blur(6px)" }}
          exit={{ opacity: 0, backdropFilter: "blur(0px)" }}
          transition={backdropTransition}
          onClick={requestClose}
        >
          <motion.div
            ref={panelRef}
            className="protocol-modal-panel factory-reset-panel"
            role="dialog"
            aria-modal="true"
            aria-label="Réinitialiser la ferme"
            tabIndex={-1}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={panelTransition}
            onClick={(e) => e.stopPropagation()}
          >
            <button className="protocol-modal-close" onClick={requestClose} aria-label="Fermer" disabled={submitting}>
              <X size={18} strokeWidth={2} />
            </button>

            <div className="factory-reset-body">
              <div className="factory-reset-icon"><AlertTriangle size={22} strokeWidth={1.8} /></div>

              {step === "credentials" ? (
                <>
                  <h2>Réinitialiser la ferme</h2>
                  <p className="factory-reset-lead">
                    Cette action nécessite les identifiants de l'administrateur de la ferme. Il
                    s'agit d'une vérification unique — elle ne vous connecte pas.
                  </p>
                  <label className="field factory-reset-field">
                    <span>Email de l'administrateur</span>
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      autoComplete="off"
                      autoFocus
                      disabled={submitting}
                    />
                  </label>
                  <label className="field factory-reset-field">
                    <span>Mot de passe</span>
                    <input
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      autoComplete="off"
                      disabled={submitting}
                    />
                  </label>
                  {error && <p className="protocol-modal-error factory-reset-error">{error}</p>}
                  <div className="factory-reset-actions">
                    <button className="add-button" onClick={requestClose} disabled={submitting}>Annuler</button>
                    <button
                      className="delete-button factory-reset-continue"
                      onClick={handleVerifyCredentials}
                      disabled={!email || !password || submitting}
                    >
                      {submitting ? <Loader2 size={16} className="spin" /> : "Continuer"}
                    </button>
                  </div>
                </>
              ) : step === "explain" ? (
                <>
                  <h2>Réinitialiser la ferme</h2>
                  <p className="factory-reset-lead">
                    Cette action est <strong>définitive et irréversible</strong>. Elle supprime
                    immédiatement et pour toujours :
                  </p>
                  <ul className="factory-reset-list">
                    {WIPED_CATEGORIES.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                  <p className="factory-reset-lead">
                    Après cette action, la base de données sera aussi vide qu'à l'installation —
                    {isPreLogin ? " vous serez redirigé vers l'écran d'accueil." : " vous serez déconnecté et redirigé vers l'écran d'accueil."}
                  </p>
                  <p className="factory-reset-lead">
                    Une sauvegarde automatique est prise chaque nuit (voir le README) — les
                    données d'hier sont donc déjà protégées. Pour conserver aussi les données
                    d'aujourd'hui, exécutez <code>python manage.py backup_db</code> avant de
                    continuer.
                  </p>
                  <div className="factory-reset-actions">
                    <button className="add-button" onClick={requestClose}>Annuler</button>
                    <button className="delete-button factory-reset-continue" onClick={() => setStep("confirm")}>
                      Continuer
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <h2>Confirmer la réinitialisation</h2>
                  <p className="factory-reset-lead">
                    Pour confirmer, saisissez le nom exact de la ferme
                    {isPreLogin ? "." : " puis votre mot de passe."}
                  </p>
                  <label className="field factory-reset-field">
                    <span>Nom de la ferme ({farmName})</span>
                    <input
                      value={farmNameInput}
                      onChange={(e) => setFarmNameInput(e.target.value)}
                      autoComplete="off"
                      autoFocus
                      disabled={submitting}
                      aria-invalid={nameMismatch}
                    />
                    {nameMismatch && (
                      <span className="field-error" style={{ margin: "4px 0 0", fontSize: 12 }}>
                        Ne correspond pas au nom exact : « {farmName} ».
                      </span>
                    )}
                  </label>
                  {!isPreLogin && (
                    <label className="field factory-reset-field">
                      <span>Votre mot de passe</span>
                      <input
                        type="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        autoComplete="current-password"
                        disabled={submitting}
                      />
                    </label>
                  )}
                  {error && <p className="protocol-modal-error factory-reset-error">{error}</p>}
                  <div className="factory-reset-actions">
                    <button className="add-button" onClick={requestClose} disabled={submitting}>Annuler</button>
                    <button className="delete-button factory-reset-continue" onClick={handleConfirm} disabled={submitting}>
                      {submitting ? <Loader2 size={16} className="spin" /> : "Réinitialiser la ferme"}
                    </button>
                  </div>
                </>
              )}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
