import { Bird, Egg, TriangleAlert, Package, Syringe, Thermometer, Clock, Wallet, Plus, ChevronRight, Home } from "lucide-react";
import "../styles/house-protocol-theme-light.css";
import "../styles/dashboard-theme.css";

const QUICK_ACTIONS = [
  { icon: Plus, label: "Nouvelle bande", hint: "Attribuer un bâtiment et une race", path: "new-batch" },
  { icon: Bird, label: "Protocole du bâtiment", hint: "Plans d'alimentation, de santé, de vaccination", path: "protocol" },
  { icon: Package, label: "Paramètres de stock", hint: "Seuils, unités, prix", path: "/dashboard/stock" },
  { icon: Wallet, label: "Aperçu financier", hint: "Dépenses, ventes, marge par bande", path: "/dashboard/finance" },
];

const ALERT_ICONS = { LOW_STOCK: Package, VACCINE_DUE: Syringe, CONSUMPTION_DEVIATION: TriangleAlert, SANITARY_VOID_END: Clock };

// house.type comes from DashboardShell's TYPE_LABELS ("Broiler"/"Pullet"/"Layer",
// English display strings also used for icon-selection comparisons elsewhere) —
// translated only here, at the one place it's shown as text.
const HOUSE_TYPE_LABELS = { Broiler: "Poulet de chair", Pullet: "Poulette", Layer: "Pondeuse" };

function StatusPill({ status }) {
  if (status === "void") return <span className="status-pill void">Vide sanitaire</span>;
  return <span className="status-pill active">Actif</span>;
}

function timeAgo(isoDate) {
  if (!isoDate) return "";
  const diffMs = Date.now() - new Date(isoDate).getTime();
  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 1) return "À l'instant";
  if (minutes < 60) return `il y a ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `il y a ${hours} h`;
  return new Date(isoDate).toLocaleDateString();
}

/**
 * Dashboard overview page (/dashboard) — stat cards, house list, recent alerts, quick actions.
 * Added mid-build (see root README.md "Autonomous decisions") and wired to real API data as-is;
 * the caller is responsible for shaping `houses`/`alerts`/`stats` from the raw API responses.
 *
 * @param {string} [farmName] - Displayed in the greeting subtitle ("Here's how {farmName} is doing…").
 * @param {Object[]} [houses] - `[{ houseCode, name, type, day, cycle, count, capacity, status }]`
 *   — derived from GET /api/houses/ plus each house's active batch (day = days since batch
 *   start, cycle = planned cycle length in days, status = "active" | "void").
 * @param {Object[]} [alerts] - `[{ id, severity, ruleType, message, triggeredAt }]` — from
 *   GET /api/alerts/, most recent first.
 * @param {?{activeBatches: number, totalBirds: number, weeklyMortalityPct: ?number, openAlerts: number}} [stats] -
 *   Precomputed stat-card values; falls back to deriving `activeBatches`/`totalBirds`/`openAlerts`
 *   from `houses`/`alerts` when null. `weeklyMortalityPct` has no such fallback — it renders as
 *   "—" when not provided, since no farm-wide weekly-mortality aggregate endpoint exists (see
 *   root README.md "Autonomous decisions" and docs/deviations.md).
 * @param {(path: string) => void} [onNavigate] - Called with a route path (or, for two quick
 *   actions, a page-relative action id like "new-batch"/"protocol") when a card/button is clicked.
 */
export default function HomeDashboard({ farmName = "Winchicken", houses = [], alerts = [], stats = null, onNavigate }) {
  const activeBatches = stats?.activeBatches ?? houses.filter((h) => h.status === "active").length;
  const totalBirds = stats?.totalBirds ?? houses.reduce((sum, h) => sum + (h.count || 0), 0);
  const weeklyMortalityPct = stats?.weeklyMortalityPct;
  const openAlerts = stats?.openAlerts ?? alerts.length;

  return (
    <div className="page-wrap">
      <div className="brand-row">
        <span className="brand-mark">
          <Home size={20} strokeWidth={1.8} />
        </span>
        <div>
          <p className="eyebrow">WINCHICKEN</p>
          <p className="brand-subtitle">Vue d'ensemble de la ferme</p>
        </div>
        <div className="header-stat">
          <span className="status-dot" />
          <span>{activeBatches} bâtiment{activeBatches === 1 ? "" : "s"} actif{activeBatches === 1 ? "" : "s"}</span>
        </div>
      </div>

      <div className="intro">
        <p>Bonjour</p>
        <span>Voici comment se porte {farmName} aujourd'hui, tous bâtiments confondus.</span>
      </div>

      <div className="stat-grid">
        <div className="stat-card">
          <p className="stat-label">Bandes actives</p>
          <p className="stat-value">{activeBatches}</p>
          <p className="stat-delta">{houses.filter((h) => h.status === "void").length} bâtiment(s) en vide sanitaire</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">Effectif total</p>
          <p className="stat-value">{totalBirds.toLocaleString()}</p>
          <p className="stat-delta">Sur {activeBatches} bâtiment{activeBatches === 1 ? "" : "s"} actif{activeBatches === 1 ? "" : "s"}</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">Mortalité hebdomadaire</p>
          <p className="stat-value">{weeklyMortalityPct != null ? `${weeklyMortalityPct}%` : "—"}</p>
          <p className="stat-delta">Référence : 3-5% en fin de cycle</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">Alertes ouvertes</p>
          <p className={`stat-value ${openAlerts > 0 ? "danger" : ""}`}>{openAlerts}</p>
          <p className={`stat-delta ${openAlerts > 0 ? "down" : ""}`}>
            {openAlerts > 0 ? `${openAlerts} à traiter` : "Tout est en ordre"}
          </p>
        </div>
      </div>

      <div className="section-row">
        <h2>Bâtiments</h2>
        <button className="section-link" onClick={() => onNavigate?.("/dashboard/houses")}>
          Voir tout <ChevronRight size={14} strokeWidth={2} />
        </button>
      </div>
      {houses.length === 0 ? (
        <p className="empty-state">1 bâtiment configuré — démarrez une bande pour le voir ici.</p>
      ) : (
        <div className="house-list">
          {houses.map((house) => {
            const Icon = house.type === "Layer" ? Egg : Bird;
            const progress = house.cycle ? Math.round((house.day / house.cycle) * 100) : 100;
            return (
              <button
                key={house.houseCode}
                className="house-item"
                onClick={() => onNavigate?.(`/dashboard/houses/${house.houseCode}`)}
              >
                <div className="house-item-main">
                  <span className="house-avatar">
                    <Icon size={18} strokeWidth={1.8} />
                  </span>
                  <div>
                    <p className="house-name">{house.name}</p>
                    <p className="house-sub">
                      {house.status === "void"
                        ? "Vide sanitaire"
                        : `${HOUSE_TYPE_LABELS[house.type] || "Bâtiment"} · jour ${house.day}${house.cycle ? ` sur ${house.cycle}` : ""} · ${house.count}/${house.capacity} volailles`}
                    </p>
                  </div>
                </div>
                <div className="house-meta">
                  {house.status === "active" && (
                    <div className="house-progress">
                      <div className="house-progress-fill" style={{ width: `${progress}%` }} />
                    </div>
                  )}
                  <StatusPill status={house.status} />
                  <ChevronRight size={16} strokeWidth={1.8} color="var(--muted)" />
                </div>
              </button>
            );
          })}
        </div>
      )}

      <div className="section-row">
        <h2>Alertes récentes</h2>
        <button className="section-link" onClick={() => onNavigate?.("/dashboard/alerts")}>
          Voir tout <ChevronRight size={14} strokeWidth={2} />
        </button>
      </div>
      {alerts.length === 0 ? (
        <p className="empty-state">Aucune alerte pour le moment.</p>
      ) : (
        <div className="alert-feed">
          {alerts.map((alert) => {
            const Icon = ALERT_ICONS[alert.ruleType] || Thermometer;
            return (
              <div key={alert.id} className={`alert-item ${alert.severity}`}>
                <span className={`alert-icon ${alert.severity}`}>
                  <Icon size={15} strokeWidth={1.8} />
                </span>
                <div className="alert-text">
                  <p>{alert.message}</p>
                  <span>{timeAgo(alert.triggeredAt)}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="section-row">
        <h2>Actions rapides</h2>
      </div>
      <div className="quick-actions">
        {QUICK_ACTIONS.map((action) => {
          const Icon = action.icon;
          return (
            <button key={action.label} className="quick-action" onClick={() => onNavigate?.(action.path)}>
              <span className="quick-action-icon">
                <Icon size={17} strokeWidth={1.8} />
              </span>
              <p>{action.label}</p>
              <span>{action.hint}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
