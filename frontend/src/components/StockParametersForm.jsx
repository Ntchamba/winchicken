import { useState } from "react";
import { Package, Plus, Trash2, Loader2 } from "lucide-react";
import "../styles/house-protocol-theme-light.css";

const TABS = ["feed", "veterinary", "equipment", "bedding"];
const CATEGORY_BY_TAB = { feed: "FEED", veterinary: "VETERINARY", equipment: "EQUIPMENT", bedding: "BEDDING" };

const PANEL_META = {
  feed: { title: "Aliment", note: "Rations par stade suivies pour cet entrepôt." },
  veterinary: { title: "Vétérinaire", note: "Vaccins et traitements — signalez les articles à chaîne du froid." },
  equipment: { title: "Équipement", note: "Ratios et seuils de réapprovisionnement pour le matériel." },
  bedding: { title: "Litière", note: "Matériaux de litière et seuils de réapprovisionnement." },
};

// feed's values stay English — .toUpperCase() feeds `feed_stage` (backend FeedStage enum)
// directly. FEED_STAGE_LABELS is the French label shown instead of the raw value.
const DETAIL_OPTIONS = {
  feed: ["Starter", "Grower", "Finisher", "Pullet", "Layer"],
  veterinary: ["Chaîne du froid : Oui", "Chaîne du froid : Non"],
  equipment: ["Pour 5 volailles", "Pour 10 volailles", "Pour 15 volailles", "Pour 250 volailles"],
  bedding: ["Bois tendre", "Bois dur", "Paille", "Balle de riz"],
};
const FEED_STAGE_LABELS = { Starter: "Démarrage", Grower: "Croissance", Finisher: "Finition", Pullet: "Poulette", Layer: "Pondeuse" };

const UNITS = ["kg", "L", "dose", "unité", "sac"];

let nextId = 100;
const makeRow = (overrides = {}) => ({
  id: nextId++,
  item: "",
  detail: DETAIL_OPTIONS.feed[0],
  threshold: 0,
  unit: UNITS[0],
  price: 0,
  ...overrides,
});

const EMPTY_DATA = { feed: [], veterinary: [], equipment: [], bedding: [] };

/**
 * Stock parameters editor — 4 category tabs (feed/veterinary/equipment/bedding), each a table of
 * StockItem-shaped rows with alert threshold and unit price. Used both for onboarding step 2 and
 * for editing the farm's stock parameters from /dashboard/stock.
 *
 * @param {Object} [initialData] - `{ feed: [...], veterinary: [...], equipment: [...], bedding: [...] }`,
 *   each row shaped like `{ id, item, detail, threshold, unit, price, itemCode? }`. Empty for
 *   onboarding (spec 7.4); pre-filled with the farm's real StockItem rows when reused from
 *   /dashboard/stock (spec 8.4).
 * @param {Object} [warehouse] - `{ name, currency, leadTime, leadTimeUnit }` seed values for the
 *   warehouse header fields (display-only concepts — `warehouseName`/`currency`/`leadTime` are
 *   NOT part of the StockItem model and are not persisted anywhere by
 *   `PUT /api/farms/{farmId}/stock-items/`, which only accepts `items`).
 * @param {"onboarding"|"management"} [mode] - "onboarding" shows Retour/Suivant; "management"
 *   shows a single "Enregistrer" bar with an inline "Saved" confirmation (spec section 4.4).
 * @param {boolean} [saving] - Disables the save/next/back buttons and shows a spinner while a
 *   save request is in flight.
 * @param {(payload: {warehouseName: string, currency: string, leadTime: number, leadTimeUnit: string, items: object[]}) => Promise<void>} [onSave] -
 *   Called with the full form payload on Save/Next; `items` entries match
 *   `StockItemSerializer`'s field names (item_code, category, name, unit, feed_stage,
 *   cold_chain_required, alert_threshold, unit_price) — only `items` maps to real backend fields.
 * @param {() => void} [onBack] - Called when "Back" is clicked (onboarding mode only).
 */
export default function StockParametersForm({
  initialData = EMPTY_DATA,
  warehouse = {},
  mode = "management",
  saving = false,
  onSave,
  onBack,
}) {
  const [warehouseName, setWarehouseName] = useState(warehouse.name || "Main store");
  const [currency, setCurrency] = useState(warehouse.currency || "XAF");
  const [leadTime, setLeadTime] = useState(warehouse.leadTime ?? 3);
  const [leadTimeUnit, setLeadTimeUnit] = useState(warehouse.leadTimeUnit || "Days");
  const [activeTab, setActiveTab] = useState("feed");
  const [data, setData] = useState(initialData);
  const [saveMessage, setSaveMessage] = useState("");

  const rows = data[activeTab];
  const totalItems = Object.values(data).reduce((sum, arr) => sum + arr.length, 0);

  const updateRow = (rowId, field, value) => {
    setData((prev) => ({
      ...prev,
      [activeTab]: prev[activeTab].map((r) => (r.id === rowId ? { ...r, [field]: value } : r)),
    }));
  };

  const addRow = () => {
    setData((prev) => ({
      ...prev,
      [activeTab]: [...prev[activeTab], makeRow({ detail: DETAIL_OPTIONS[activeTab][0] })],
    }));
  };

  const deleteRow = (rowId) => {
    setData((prev) => ({ ...prev, [activeTab]: prev[activeTab].filter((r) => r.id !== rowId) }));
  };

  const buildPayload = () => ({
    warehouseName,
    currency,
    leadTime,
    leadTimeUnit,
    items: Object.entries(data).flatMap(([tab, tabRows]) =>
      tabRows.map((row) => ({
        item_code: row.itemCode,
        category: CATEGORY_BY_TAB[tab],
        name: row.item,
        unit: row.unit,
        feed_stage: tab === "feed" ? row.detail.toUpperCase() : "NOT_APPLICABLE",
        cold_chain_required: tab === "veterinary" ? row.detail === "Chaîne du froid : Oui" : false,
        alert_threshold: Number(row.threshold) || 0,
        unit_price: Number(row.price) || 0,
      }))
    ),
  });

  const handleSave = async () => {
    if (!onSave) return;
    await onSave(buildPayload());
    setSaveMessage("Enregistré");
    setTimeout(() => setSaveMessage(""), 3000);
  };

  const handleNext = async () => {
    if (onSave) await onSave(buildPayload());
  };

  return (
    <div className="page-wrap">
      <div className="brand-row">
        <span className="brand-mark">
          <Package size={20} strokeWidth={1.8} />
        </span>
        <div>
          <p className="eyebrow">WINCHICKEN</p>
          <p className="brand-subtitle">Paramètres de stock</p>
        </div>
        <div className="header-stat">
          <span className="status-dot" />
          <span>{totalItems} article(s) suivi(s)</span>
        </div>
      </div>

      <div className="intro">
        <p>Configurez votre stock</p>
        <span>
          Définissez les seuils d'alerte, les unités et les prix pour chaque article stocké dans l'entrepôt —
          aliment, vétérinaire, équipement et litière.
        </span>
      </div>

      <div className="card house-card">
        <div className="section-heading">
          <div>
            <span className="house-chip">ENTREPÔT</span>
            <h1 style={{ margin: "7px 0 0", fontFamily: "'Space Grotesk',sans-serif", fontSize: 22, letterSpacing: "-.03em" }}>
              {warehouseName || "Entrepôt sans nom"}
            </h1>
          </div>
        </div>
        <div className="detail-grid">
          <label className="field">
            <span>Nom de l'entrepôt</span>
            <input value={warehouseName} onChange={(e) => setWarehouseName(e.target.value)} />
          </label>
          <label className="field">
            <span>Devise</span>
            <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
              <option>XAF</option>
              <option>USD</option>
              <option>EUR</option>
            </select>
          </label>
          <label className="field">
            <span>Délai de réapprovisionnement</span>
            <div className="inline-field">
              <input type="number" value={leadTime} onChange={(e) => setLeadTime(e.target.value)} />
              <select value={leadTimeUnit} onChange={(e) => setLeadTimeUnit(e.target.value)}>
                <option value="Days">Jours</option>
                <option value="Weeks">Semaines</option>
              </select>
            </div>
          </label>
        </div>
      </div>

      <div className="tabs">
        {TABS.map((tab) => (
          <button
            key={tab}
            className={`tab ${tab === activeTab ? "active" : ""}`}
            onClick={() => setActiveTab(tab)}
          >
            {PANEL_META[tab].title}
            <span className="tab-count">{data[tab].length}</span>
          </button>
        ))}
      </div>

      <div className="card schedule-card">
        <div className="schedule-heading">
          <div>
            <span className="section-kicker">CATÉGORIE</span>
            <h2>{PANEL_META[activeTab].title}</h2>
            <p className="schedule-note">{PANEL_META[activeTab].note}</p>
          </div>
        </div>

        <div className="table-head">
          <span>Article</span>
          <span>Détail</span>
          <span>Seuil d'alerte</span>
          <span>Prix unitaire</span>
          <span />
        </div>

        <div className="rows">
          {rows.map((row) => (
            <div key={row.id} className="schedule-row">
              <input
                value={row.item}
                onChange={(e) => updateRow(row.id, "item", e.target.value)}
                placeholder="Nom de l'article"
              />
              <select value={row.detail} onChange={(e) => updateRow(row.id, "detail", e.target.value)}>
                {DETAIL_OPTIONS[activeTab].map((d) => (
                  <option key={d} value={d}>{activeTab === "feed" ? FEED_STAGE_LABELS[d] || d : d}</option>
                ))}
              </select>
              <div className="bound-input">
                <input
                  type="number"
                  value={row.threshold}
                  onChange={(e) => updateRow(row.id, "threshold", e.target.value)}
                />
                <select value={row.unit} onChange={(e) => updateRow(row.id, "unit", e.target.value)}>
                  {UNITS.map((u) => (
                    <option key={u}>{u}</option>
                  ))}
                </select>
              </div>
              <input
                value={row.price}
                onChange={(e) => updateRow(row.id, "price", e.target.value)}
                placeholder="Prix unitaire"
              />
              <button className="delete-button" aria-label="Supprimer l'article" onClick={() => deleteRow(row.id)}>
                <Trash2 size={16} strokeWidth={1.8} />
              </button>
            </div>
          ))}
          {rows.length === 0 && <p className="empty-state">Aucun article dans cette catégorie pour le moment.</p>}
        </div>

        <button className="add-button" onClick={addRow}>
          <Plus size={14} strokeWidth={2.5} />
          Ajouter un article
        </button>
      </div>

      {mode === "onboarding" ? (
        <div className="save-bar">
          {onBack && (
            <button className="add-button" onClick={onBack} disabled={saving}>
              Retour
            </button>
          )}
          <span style={{ flex: 1 }} />
          <button className="save-button" onClick={handleNext} disabled={saving || totalItems === 0}>
            {saving ? <Loader2 size={16} className="spin" /> : "Suivant"}
          </button>
        </div>
      ) : (
        <div className="save-bar">
          <span className={`save-message ${saveMessage ? "success" : ""}`}>{saveMessage}</span>
          <button className="save-button" onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 size={16} className="spin" /> : "Enregistrer les paramètres"}
          </button>
        </div>
      )}
    </div>
  );
}
