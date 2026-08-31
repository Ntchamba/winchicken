import { useState } from "react";
import { Bell, Loader2, Settings } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import useWebPush from "../../hooks/useWebPush";
import FactoryResetModal from "../../components/FactoryResetModal";
import "../../styles/dashboard-theme.css";

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

      <div className="card house-card" style={{ marginTop: 18 }}>
        <h2 style={{ display: "flex", alignItems: "center", gap: 8, margin: "0 0 6px" }}>
          <Bell size={18} strokeWidth={1.8} /> Notifications bureau
        </h2>
        <p className="schedule-note">
          Recevez une notification sur ce PC à chaque événement (tâche du jour à son créneau,
          alerte, mouvement de stock, écriture financière, cas ou panne signalés) — même quand
          aucun onglet Winchicken n'est ouvert.
        </p>

        {!push.supported && (
          <p className="field-error" style={{ marginTop: 10 }}>
            Ce navigateur ne prend pas en charge les notifications push.
          </p>
        )}
        {push.supported && !push.enabled && (
          <p className="field-error" style={{ marginTop: 10 }}>
            Le serveur n'est pas encore configuré pour le push (clés VAPID manquantes).
          </p>
        )}
        {push.supported && push.permission === "denied" && (
          <p className="field-error" style={{ marginTop: 10 }}>
            Les notifications sont bloquées pour ce site dans les réglages du navigateur —
            réautorisez-les puis rechargez la page.
          </p>
        )}
        {push.error && <p className="field-error" style={{ marginTop: 10 }}>{push.error}</p>}

        {push.supported && push.enabled && push.permission !== "denied" && (
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 12 }}>
            {push.subscribed ? (
              <>
                <span className="schedule-note" style={{ color: "var(--success, #16a34a)" }}>
                  Activées sur ce PC.
                </span>
                <button className="add-button" style={{ marginTop: 0 }} onClick={push.disable} disabled={push.busy}>
                  {push.busy ? <Loader2 size={14} className="spin" /> : "Désactiver"}
                </button>
              </>
            ) : (
              <button className="save-button" style={{ width: "auto" }} onClick={push.enable} disabled={push.busy}>
                {push.busy ? <Loader2 size={16} className="spin" /> : "Activer les notifications bureau"}
              </button>
            )}
          </div>
        )}
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
