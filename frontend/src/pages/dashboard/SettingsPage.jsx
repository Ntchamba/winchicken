import { Settings } from "lucide-react";
import { useAuth } from "../../context/AuthContext";

// user.role from GET /api/auth/me/ is the raw backend enum — displayed only through
// this French label map, never shown raw.
const ROLE_LABELS = {
  ADMIN: "Administrateur", SECONDARY_ADMIN: "Administrateur secondaire", FARM_MANAGER: "Gérant de ferme",
  FARMER: "Fermier", WORKER: "Ouvrier", TECHNICIAN: "Technicien", CASHIER: "Caissier",
};

export default function SettingsPage() {
  const { user } = useAuth();

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
    </div>
  );
}
