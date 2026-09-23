import { useState } from "react";
import { Bell, CheckCircle2, Loader2, Settings } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import useWebPush from "../../hooks/useWebPush";
import FactoryResetModal from "../../components/FactoryResetModal";
import InstallAppCard from "../../components/InstallAppCard";
import "../../styles/dashboard-theme.css";
import QuickLinksBar from "../../components/QuickLinksBar";

// user.role from GET /api/auth/me/ is the raw backend enum — displayed only through
// this French label map, never shown raw.
const ROLE_LABELS = {
  ADMIN: "Administrateur", SECONDARY_ADMIN: "Administrateur secondaire", FARM_MANAGER: "Gérant de ferme",
  FARMER: "Fermier", WORKER: "Ouvrier", TECHNICIAN: "Technicien", CASHIER: "Caissier",
};

export default function SettingsPage() {
  useDocumentTitle("Paramètres");
  const { user } = useAuth();
  const [resetOpen, setResetOpen] = useState(false);
  const push = useWebPush();

  return (
    <div className="page-wrap">
      <QuickLinksBar />
      <div className="brand-row">
        <span className="brand-mark"><Settings size={20} strokeWidth={1.8} /></span>
        <div>
          <p className="eyebrow">WINCHICKEN</p>
          <p className="brand-subtitle">Paramètres du compte</p>
        </div>
      </div>

      <div className="card house-card" style={{ marginTop: 18 }}>
        <div className="detail-grid">
          <label className="field"><span>Nom</span><input value={user.name} disabled /></label>
          <label className="field"><span>Email</span><input value={user.email} disabled /></label>
          <label className="field"><span>Rôle</span><input value={ROLE_LABELS[user.role] || user.role} disabled /></label>
        </div>
        <p className="schedule-note" style={{ marginTop: 14 }}>
          Ferme : {user.farm_name} — contactez un administrateur pour modifier les informations du compte.
        </p>
      </div>

      <InstallAppCard />

      <div className="card house-card" style={{ marginTop: 18 }}>
        <h2 style={{ display: "flex", alignItems: "center", gap: 8, margin: "0 0 6px" }}>
          <Bell size={18} strokeWidth={1.8} /> Notifications bureau
        </h2>
        <p className="schedule-note">
          Recevez une notification sur ce PC à chaque événement (tâche du jour à son créneau,
          alerte, mouvement de stock, écriture financière, cas ou panne signalés) — même quand
          aucun onglet Winchicken n'est ouvert. Sans effet sur les autres canaux d'alerte.
        </p>

        {!push.supported && (
          <p className="field-error" style={{ marginTop: 10 }}>
            Ce navigateur ne prend pas en charge les notifications push.
          </p>
        )}

        {/* denied — no JS API can re-prompt; the user must unblock in browser settings */}
        {push.supported && push.permission === "denied" && (
          <div className="field-error" style={{ marginTop: 12 }}>
            <p style={{ margin: 0, fontWeight: 600 }}>Notifications bloquées par le navigateur</p>
            <p className="schedule-note" style={{ marginTop: 6 }}>
              Une fois bloquées, aucune page ne peut les redemander. Pour les réautoriser :
            </p>
            <ol className="schedule-note" style={{ margin: "6px 0 0", paddingLeft: 18 }}>
              <li>Cliquez sur l'icône du site à gauche de la barre d'adresse.</li>
              <li>Ouvrez « Notifications ».</li>
              <li>Choisissez « Autoriser », puis rechargez la page.</li>
            </ol>
          </div>
        )}

        {/* granted — informational, not a call to action */}
        {push.supported && push.permission === "granted" && (
          <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 10, marginTop: 12 }}>
            <CheckCircle2 size={18} strokeWidth={2} style={{ color: "var(--success, #16a34a)", flexShrink: 0 }} />
            <span className="schedule-note" style={{ color: "var(--success, #16a34a)", margin: 0 }}>
              Notifications activées{push.subscribed ? " sur ce PC" : ""}.
            </span>
            {push.subscribed && (
              <button className="add-button" style={{ marginTop: 0 }} onClick={push.disable} disabled={push.busy}>
                {push.busy ? <Loader2 size={14} className="spin" /> : "Ne plus recevoir sur ce PC"}
              </button>
            )}
            {!push.subscribed && push.enabled && (
              <button className="add-button" style={{ marginTop: 0 }} onClick={push.enable} disabled={push.busy}>
                {push.busy ? <Loader2 size={14} className="spin" /> : "Recevoir sur ce PC"}
              </button>
            )}
          </div>
        )}

        {/* default — the only actionable opt-in; requestPermission() fires from this click */}
        {push.supported && push.permission === "default" && (
          <button
            className="save-button"
            style={{ width: "auto", marginTop: 12 }}
            onClick={push.enable}
            disabled={push.busy}
          >
            {push.busy ? <Loader2 size={16} className="spin" /> : "Activer les notifications"}
          </button>
        )}

        {push.supported && !push.enabled && push.permission !== "denied" && (
          <p className="schedule-note" style={{ marginTop: 10 }}>
            Serveur pas encore configuré pour l'envoi (clés VAPID manquantes) — l'autorisation du
            navigateur peut être accordée dès maintenant, la réception suivra.
          </p>
        )}

        {push.error && <p className="field-error" style={{ marginTop: 10 }}>{push.error}</p>}
      </div>

      {user.role === "ADMIN" && (
        <div className="danger-zone">
          <h2>Zone dangereuse</h2>
          <p>Ces actions sont irréversibles. Procédez avec une extrême prudence.</p>
          <div className="danger-zone-action">
            <div>
              <strong>Réinitialiser la ferme</strong>
              <span>Supprime définitivement toutes les données de la ferme et tous les comptes, y compris le vôtre.</span>
            </div>
            <button className="danger-zone-button" onClick={() => setResetOpen(true)}>
              Réinitialiser la ferme
            </button>
          </div>
        </div>
      )}

      <FactoryResetModal open={resetOpen} onClose={() => setResetOpen(false)} />
    </div>
  );
}
