import { Bird, Egg, TriangleAlert, Package, Syringe, Thermometer, Clock, Wallet, Plus, ChevronRight, Home, Scale } from "lucide-react";
import GrowthCurves from "./GrowthCurves";
import QuickEntryPanel from "./QuickEntryPanel";
import FarmHealthBadge from "./FarmHealthBadge";
import IncidentsPanel from "./IncidentsPanel";
import Upcoming48hWidget from "./Upcoming48hWidget";
import "../styles/house-protocol-theme-light.css";
import "../styles/dashboard-theme.css";
import "../styles/protocol-edit-modal.css";
import "./weighing-links.css";

const QUICK_ACTIONS = [
  { icon: Plus, label: "Nouvelle bande", hint: "Attribuer un bâtiment et une race", path: "new-batch" },
  { icon: Package, label: "Paramètres de stock", hint: "Seuils, unités, prix", path: "/dashboard/stock" },
  { icon: Wallet, label: "Aperçu financier", hint: "Dépenses, ventes, marge par bande", path: "/dashboard/finances" },
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
 * @param {(path: string) => void} [onNavigate] - Called with a route path (or, for one quick
 *   action, a page-relative action id like "new-batch") when a card/button is clicked.
 * @param {Object[]} [growthSeries] - `[{batchCode, batchName, points}]` from
 *   GET /api/batches/growth-curves/ — passed straight through to `GrowthCurves` (2026-08-25,
 *   replaces the protocol form as this screen's primary content; see root README.md).
 * @param {Object[]} [activeBatchList] - `[{batchCode, name, houseCode, houseName}]` — every
 *   active batch, rendered as a small list with a "Modifier" button per row (opens the protocol
 *   editor for that batch's house).
 * @param {(houseCode: string) => void} [onModifyBatch] - Called with a house code when a
 *   "Modifier" button is clicked.
 * @param {() => void} [onDailyLogged] - Called after the quick-entry panel successfully saves a
 *   day's mortality/eggs, so the caller can refetch `growthSeries`.
 */
export default function HomeDashboard({
  farmName = "Winchicken", houses = [], alerts = [], stats = null, onNavigate,
  growthSeries = [], activeBatchList = [], onModifyBatch, onDailyLogged, loading = false, alertsLoading = false,
}) {
  // While loading, figures read "—" rather than 0: "0 bande" or "Tout est en ordre" before the
  // data has arrived is a false answer, not a placeholder (phone audit, 2026-09-25).
  const pending = (value) => (loading ? "—" : value);
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
          <span>{loading ? "Chargement…" : `${activeBatches} bâtiment${activeBatches === 1 ? "" : "s"} actif${activeBatches === 1 ? "" : "s"}`}</span>
        </div>
      </div>

      <div className="intro">
        <p>Bonjour</p>
        <span>Voici comment se porte {farmName} aujourd'hui, tous bâtiments confondus.</span>
      </div>

      <FarmHealthBadge />

      <IncidentsPanel />

      <div className="stat-grid">
        <div className="stat-card">
          <p className="stat-label">Bandes actives</p>
          <p className="stat-value">{pending(activeBatches)}</p>
          <p className="stat-delta">{loading ? "Chargement…" : `${houses.filter((h) => h.status === "void").length} bâtiment(s) en vide sanitaire`}</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">Effectif total</p>
          <p className="stat-value">{pending(totalBirds.toLocaleString())}</p>
          <p className="stat-delta">{loading ? "Chargement…" : `Sur ${activeBatches} bâtiment${activeBatches === 1 ? "" : "s"} actif${activeBatches === 1 ? "" : "s"}`}</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">Mortalité hebdomadaire</p>
          <p className="stat-value">{weeklyMortalityPct != null ? `${weeklyMortalityPct}%` : "—"}</p>
          <p className="stat-delta">Référence : 3-5% en fin de cycle</p>
        </div>
        <div className="stat-card">
          <p className="stat-label">Alertes ouvertes</p>
          <p className={`stat-value ${openAlerts > 0 ? "danger" : ""}`}>{alertsLoading ? "—" : openAlerts}</p>
          <p className={`stat-delta ${openAlerts > 0 ? "down" : ""}`}>
            {alertsLoading ? "Chargement…" : openAlerts > 0 ? `${openAlerts} à traiter` : "Tout est en ordre"}
          </p>
        </div>
      </div>

      <Upcoming48hWidget onNavigate={onNavigate} />

      <div className="section-row"><h2>Croissance et survie — toutes bandes actives</h2></div>
      {loading ? <p className="empty-state">Chargement…</p> : <GrowthCurves series={growthSeries} scope="all" />}

      {/* Weighing moved to each house's "Pesée" page (2026-09-23), next to the curve it feeds;
          this keeps the one-tap path to it from here instead of a second copy of the form. */}
      <div className="section-row"><h2>Pesée</h2></div>
      {loading ? (
        <p className="empty-state">Chargement…</p>
      ) : activeBatchList.length === 0 ? (
        <p className="empty-state">Aucune bande active à peser.</p>
      ) : (
        <div className="weighing-links">
          {activeBatchList.map((b) => (
            <button
              key={b.batchCode}
              type="button"
              className="weighing-link"
              onClick={() => onNavigate?.(`/dashboard/houses/${b.houseCode}/weighing`)}
            >
              <Scale size={16} strokeWidth={1.9} aria-hidden="true" />
              <span>Peser {b.name || b.batchCode}</span>
              <span className="weighing-link-house">{b.houseName}</span>
              <ChevronRight size={15} strokeWidth={2} aria-hidden="true" />
            </button>
          ))}
        </div>
      )}

      <div className="section-row"><h2>Saisie rapide du jour</h2></div>
      {loading ? (
        <p className="empty-state">Chargement…</p>
      ) : (
        <QuickEntryPanel
          batches={activeBatchList.map((b) => ({ batch_code: b.batchCode, name: b.name }))}
          onLogged={onDailyLogged}
        />
      )}

      {activeBatchList.length > 0 && (
        <>
          <div className="section-row"><h2>Bandes actives</h2></div>
          <div className="house-list" style={{ marginBottom: 18 }}>
            {activeBatchList.map((b) => (
              <div key={b.batchCode} className="house-item batch-modifier-row" style={{ cursor: "default" }}>
                <div className="house-item-main">
                  <span className="house-avatar"><Bird size={18} strokeWidth={1.8} /></span>
                  <div>
                    <p className="house-name">{b.name || b.batchCode}</p>
                    <p className="house-sub">{b.houseName} · {b.batchCode}</p>
                  </div>
                </div>
                <button className="batch-modifier-button" onClick={() => onModifyBatch?.(b.houseCode)}>
                  Modifier
                </button>
              </div>
            ))}
          </div>
        </>
      )}

      <div className="section-row">
        <h2>Bâtiments</h2>
        <button className="section-link" onClick={() => onNavigate?.("/dashboard/houses")}>
          Voir tout <ChevronRight size={14} strokeWidth={2} />
        </button>
      </div>
      {houses.length === 0 ? (
        <p className="empty-state">{loading ? "Chargement…" : "Aucun bâtiment configuré — démarrez une bande pour le voir ici."}</p>
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
        <p className="empty-state">{alertsLoading ? "Chargement…" : "Aucune alerte pour le moment."}</p>
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
