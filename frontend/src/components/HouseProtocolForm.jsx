import { useState } from "react";
import {
  Soup, Thermometer, Stethoscope, Syringe, SprayCan, ShieldCheck, Droplets, Wind, Egg, Bug,
  ClipboardList, Package, Plus, Trash2, Loader2, Sparkles, HelpCircle, X, Check,
} from "lucide-react";
import { housesApi } from "../api/endpoints";
import "../styles/house-protocol-theme-light.css";

// Curated icon picker for custom categories — kept in sync by hand with the backend's
// CUSTOM_CATEGORY_ICON_CHOICES (apps/protocols/models.py). The 5 defaults' own icons are a
// subset of this same list, so one map covers both.
const ICON_OPTIONS = [
  { name: "Soup", Icon: Soup }, { name: "Thermometer", Icon: Thermometer },
  { name: "Stethoscope", Icon: Stethoscope }, { name: "Syringe", Icon: Syringe },
  { name: "SprayCan", Icon: SprayCan }, { name: "ShieldCheck", Icon: ShieldCheck },
  { name: "Droplets", Icon: Droplets }, { name: "Wind", Icon: Wind },
  { name: "Egg", Icon: Egg }, { name: "Bug", Icon: Bug },
  { name: "ClipboardList", Icon: ClipboardList }, { name: "Package", Icon: Package },
];
const ICON_MAP = Object.fromEntries(ICON_OPTIONS.map((o) => [o.name, o.Icon]));
const iconFor = (name) => ICON_MAP[name] || ClipboardList;

// Mirrors apps.protocols.models.DEFAULT_PROTOCOL_CATEGORIES exactly (label + icon + order) —
// used as the starting category list in onboarding mode, before the house (and its real,
// backend-seeded categories) exists. `id` here is a stable local key, not a database id.
const DEFAULT_CATEGORIES = [
  { id: "default-0", label: "Alimentation", icon: "Soup" },
  { id: "default-1", label: "Température", icon: "Thermometer" },
  { id: "default-2", label: "Santé et soins", icon: "Stethoscope" },
  { id: "default-3", label: "Vaccination", icon: "Syringe" },
  { id: "default-4", label: "Nettoyage", icon: "SprayCan" },
];

// Internal values stay English to match ProtocolUnit (backend enum) — .toUpperCase()
// on these feeds `from_unit`/`to_unit` directly. Display labels are French, separately.
const UNITS = ["Day", "Week", "Month"];
const UNIT_LABELS = { Day: "Jour", Week: "Semaine", Month: "Mois" };
const UNIT_LABELS_PLURAL = { Day: "Jours", Week: "Semaines", Month: "Mois" };

let nextId = 100;
const makeRow = (overrides = {}) => ({
  id: nextId++,
  fromValue: 1,
  fromUnit: "Day",
  toValue: 1,
  toUnit: "Day",
  untilEnd: false,
  what: "",
  details: "",
  ...overrides,
});

// Reference starter template — only ever applied via the explicit "Load starter template"
// button (cahier des charges 7.3): never pre-filled automatically (no-default-data rule).
// Keyed by the 5 defaults' stable local ids, matching DEFAULT_CATEGORIES above.
const STARTER_TEMPLATE = {
  "default-0": [
    makeRow({ fromValue: 1, toValue: 15, what: "Aliment démarrage", details: "3000 kcal, 22,5% de protéines" }),
    makeRow({ fromValue: 15, toValue: 30, what: "Aliment croissance", details: "3150 kcal, 21,5% de protéines" }),
    makeRow({ fromValue: 30, untilEnd: true, what: "Aliment finition", details: "3200 kcal, 20% de protéines" }),
  ],
  "default-1": [
    makeRow({ fromValue: 1, toValue: 3, what: "Démarrage (éleveuse)", details: "Éleveuse 38°C, salle > 28°C" }),
  ],
  "default-2": [
    makeRow({ fromValue: 2, toValue: 4, what: "Anti-infectieux + vitamines", details: "Dans l'eau de boisson" }),
  ],
  "default-3": [
    makeRow({ fromValue: 1, toValue: 1, what: "Maladie de Newcastle", details: "Hitchner B1, goutte oculaire" }),
  ],
  "default-4": [
    makeRow({ fromValue: 1, fromUnit: "Day", untilEnd: true, what: "Ajout de litière", details: "+40kg au jour 7" }),
  ],
};

// One worked example per default category, shown read-only in the help panel — reuses the
// same reference content as STARTER_TEMPLATE/Demo mode, illustrative only, never written into
// the real form.
const HELP_EXAMPLES = [
  { label: "Alimentation", icon: "Soup", from: "1 Jour", to: "15 Jours", what: "Aliment démarrage", details: "3000 kcal, 22,5% de protéines" },
  { label: "Température", icon: "Thermometer", from: "1 Jour", to: "3 Jours", what: "Démarrage (éleveuse)", details: "Éleveuse 38°C, salle > 28°C" },
  { label: "Santé et soins", icon: "Stethoscope", from: "2 Jours", to: "4 Jours", what: "Anti-infectieux + vitamines", details: "Dans l'eau de boisson" },
  { label: "Vaccination", icon: "Syringe", from: "1 Jour", to: "1 Jour", what: "Maladie de Newcastle", details: "Hitchner B1, goutte oculaire" },
  { label: "Nettoyage", icon: "SprayCan", from: "1 Jour", to: "Fin de cycle", what: "Ajout de litière", details: "+40kg au jour 7" },
];

/**
 * House + protocol editor — dynamic category tabs (5 defaults + any custom ones added via
 * "+"), each a table of ProtocolTemplate-shaped rows. Used both for onboarding step 1 and for
 * editing an existing house's protocol from /dashboard/houses/{houseCode}/protocol.
 *
 * Category add/delete persist immediately (optimistic UI) in management mode, since the house
 * already exists there; in onboarding mode they stay local state until the whole form submits,
 * since the house — and therefore any real category id — doesn't exist yet. Category *delete*
 * is management-mode only (see README/docs/deviations.md): during onboarding the 5 defaults are
 * always exactly categories[0..4] by array position, which is how protocol lines get resolved
 * to a real category server-side (`categoryIndex`) before any of them have a database id —
 * removing one from the middle would break that alignment, so the control is simply not shown
 * before the house exists.
 *
 * Ships with a `STARTER_TEMPLATE` reference schedule, but it is only ever applied via the
 * explicit "Load starter template" button — never pre-filled automatically (cahier des charges
 * 7.3 "no default data" rule).
 *
 * @param {Object} [initialHeader] - `{ buildingName, chicksPlaced, growthCycle, growthCycleUnit, batchName }`
 *   seed values for the house/batch header fields.
 * @param {Object[]} [initialCategories] - `[{ id, label, icon }]` in display order. Defaults to
 *   the 5 built-in categories (onboarding — no house/real ids exist yet). Pass the house's real
 *   categories (from GET /api/houses/{houseCode}/protocol-categories/) in management mode.
 * @param {Object} [initialSchedules] - `{ [categoryId]: [...] }`, each row shaped like
 *   `{ id, fromValue, fromUnit, toValue, toUnit, untilEnd, what, details }`. Empty for
 *   onboarding (spec 7.3); pre-filled with the house's real ProtocolTemplate rows, grouped by
 *   their real category id, when reused for editing (spec 8.7).
 * @param {"onboarding"|"management"} [mode] - "onboarding" shows a "Next" button only (first
 *   wizard step, no inline save confirmation, category add/delete is local-only); "management"
 *   shows "Save protocol" with an inline "Saved" confirmation message, and category add/delete
 *   persist immediately.
 * @param {string} [houseCode] - Required in management mode — target for the live category
 *   add/delete API calls. Unused/omit in onboarding mode.
 * @param {boolean} [saving] - Disables the load-template/save buttons and shows a spinner while
 *   a save request is in flight.
 * @param {(payload: {house: object, batchName: string, categories: object[], protocolLines: object[]}) => Promise<void>} [onSave] -
 *   Called with the full form payload on Save/Next. In onboarding mode, `protocolLines` entries
 *   carry `categoryIndex` (position in the returned `categories` array) instead of a real
 *   category id; `categories` is the *full* list (5 defaults + any custom ones, in order) —
 *   the caller slices off `.slice(5)` and maps to `{label, icon}` to build the API's
 *   `customCategories` field, and keeps the full array to pre-fill the form again if the user
 *   navigates back to this step. In management mode, `protocolLines` entries carry the real
 *   `category` id directly and `categories`/`categoryIndex` aren't needed (categories already
 *   persisted via the live add/delete calls).
 * @param {string} [helpDocUrl] - Link target for the help panel's "En savoir plus" — see
 *   docs/protocol-configuration.md.
 */
export default function HouseProtocolForm({
  initialHeader = {},
  initialCategories = null,
  initialSchedules = {},
  mode = "management",
  houseCode = null,
  saving = false,
  onSave,
  helpDocUrl = "/docs/protocol-configuration.md",
}) {
  const [buildingName, setBuildingName] = useState(initialHeader.buildingName || "");
  const [chicksPlaced, setChicksPlaced] = useState(initialHeader.chicksPlaced || "");
  const [growthCycle, setGrowthCycle] = useState(initialHeader.growthCycle || 56);
  const [growthCycleUnit, setGrowthCycleUnit] = useState(initialHeader.growthCycleUnit || "Day");
  const [batchName, setBatchName] = useState(initialHeader.batchName || "");
  const [categories, setCategories] = useState(initialCategories || DEFAULT_CATEGORIES);
  const [activeCategoryId, setActiveCategoryId] = useState((initialCategories || DEFAULT_CATEGORIES)[0]?.id);
  const [schedules, setSchedules] = useState(initialSchedules);
  const [saveMessage, setSaveMessage] = useState("");
  const [helpOpen, setHelpOpen] = useState(false);

  const [addingCategory, setAddingCategory] = useState(false);
  const [newCategoryLabel, setNewCategoryLabel] = useState("");
  const [newCategoryIcon, setNewCategoryIcon] = useState(ICON_OPTIONS[0].name);
  const [categoryError, setCategoryError] = useState("");
  const [categoryBusy, setCategoryBusy] = useState(false);
  const [confirmDeleteCategory, setConfirmDeleteCategory] = useState(null);

  const rows = schedules[activeCategoryId] || [];
  const totalRows = Object.values(schedules).reduce((sum, arr) => sum + arr.length, 0);

  const updateRow = (rowId, field, value) => {
    setSchedules((prev) => ({
      ...prev,
      [activeCategoryId]: (prev[activeCategoryId] || []).map((r) => (r.id === rowId ? { ...r, [field]: value } : r)),
    }));
  };

  const addRow = () => {
    setSchedules((prev) => ({ ...prev, [activeCategoryId]: [...(prev[activeCategoryId] || []), makeRow()] }));
  };

  const deleteRow = (rowId) => {
    setSchedules((prev) => ({ ...prev, [activeCategoryId]: (prev[activeCategoryId] || []).filter((r) => r.id !== rowId) }));
  };

  const loadStarterTemplate = () => {
    setSchedules(STARTER_TEMPLATE);
  };

  const addCategory = async () => {
    const label = newCategoryLabel.trim();
    if (!label) {
      setCategoryError("Le nom de la catégorie est requis.");
      return;
    }
    setCategoryError("");
    const tempId = `pending-${Date.now()}`;
    setCategories((prev) => [...prev, { id: tempId, label, icon: newCategoryIcon }]);
    setActiveCategoryId(tempId);
    setAddingCategory(false);
    setNewCategoryLabel("");
    setNewCategoryIcon(ICON_OPTIONS[0].name);

    if (mode === "management" && houseCode) {
      try {
        const { data } = await housesApi.addProtocolCategory(houseCode, { label, icon: newCategoryIcon });
        setCategories((prev) => prev.map((c) => (c.id === tempId ? data : c)));
        setActiveCategoryId((cur) => (cur === tempId ? data.id : cur));
      } catch (err) {
        setCategories((prev) => prev.filter((c) => c.id !== tempId));
        setActiveCategoryId((cur) => (cur === tempId ? categories[0]?.id : cur));
        setCategoryError(err.response?.data?.label?.[0] || err.response?.data?.icon?.[0] || "Impossible d'ajouter la catégorie.");
      }
    }
  };

  const deleteCategory = async (category) => {
    setCategoryBusy(true);
    try {
      if (mode === "management" && houseCode) {
        await housesApi.removeProtocolCategory(houseCode, category.id);
      }
      setCategories((prev) => {
        const next = prev.filter((c) => c.id !== category.id);
        setActiveCategoryId((cur) => (cur === category.id ? next[0]?.id : cur));
        return next;
      });
      setSchedules((prev) => {
        const { [category.id]: _dropped, ...rest } = prev;
        return rest;
      });
    } finally {
      setCategoryBusy(false);
      setConfirmDeleteCategory(null);
    }
  };

  const buildPayload = () => {
    const house = { buildingName, chicksPlaced: Number(chicksPlaced) || 0, growthCycle: Number(growthCycle) || 0, growthCycleUnit };
    if (mode === "onboarding") {
      return {
        house,
        batchName,
        categories,
        protocolLines: categories.flatMap((cat, index) =>
          (schedules[cat.id] || []).map((row) => ({
            categoryIndex: index,
            from_value: Number(row.fromValue) || 0,
            from_unit: row.fromUnit.toUpperCase(),
            to_value: row.untilEnd ? null : Number(row.toValue) || 0,
            to_unit: row.toUnit.toUpperCase(),
            until_end: row.untilEnd,
            what: row.what,
            details: row.details,
          }))
        ),
      };
    }
    return {
      house,
      batchName,
      protocolLines: categories.flatMap((cat) =>
        (schedules[cat.id] || []).map((row) => ({
          category: cat.id,
          from_value: Number(row.fromValue) || 0,
          from_unit: row.fromUnit.toUpperCase(),
          to_value: row.untilEnd ? null : Number(row.toValue) || 0,
          to_unit: row.toUnit.toUpperCase(),
          until_end: row.untilEnd,
          what: row.what,
          details: row.details,
        }))
      ),
    };
  };

  const handleSave = async () => {
    if (!onSave) return;
    await onSave(buildPayload());
    if (mode !== "onboarding") {
      setSaveMessage("Enregistré");
      setTimeout(() => setSaveMessage(""), 3000);
    }
  };

  return (
    <div className="page-wrap">
      <div className="brand-row">
        <span className="brand-mark">
          <Soup size={20} strokeWidth={1.8} />
        </span>
        <div>
          <p className="eyebrow">WINCHICKEN</p>
          <p className="brand-subtitle">Protocole du bâtiment</p>
        </div>
        <button
          className="help-button"
          onClick={() => setHelpOpen(true)}
          aria-label="Aide sur le protocole"
          type="button"
        >
          <HelpCircle size={18} strokeWidth={1.8} />
        </button>
      </div>

      <div className="intro">
        <p>Planifiez le protocole du bâtiment</p>
        <span>
          Alimentation, température, santé, vaccination et nettoyage — s'applique à chaque bande démarrée dans ce
          bâtiment, sauf modification. Ajoutez vos propres catégories avec le bouton « + ».
        </span>
      </div>

      <div className="card house-card">
        <div className="section-heading">
          <div>
            <span className="house-chip">BÂTIMENT</span>
            <h1 style={{ margin: "7px 0 0", fontFamily: "'Space Grotesk',sans-serif", fontSize: 22, letterSpacing: "-.03em" }}>
              {buildingName || "Bâtiment sans nom"}
            </h1>
          </div>
          <button className="add-button" style={{ marginTop: 0 }} onClick={loadStarterTemplate} disabled={saving}>
            <Sparkles size={14} strokeWidth={2.2} />
            Charger le modèle de départ
          </button>
        </div>
        <div className="detail-grid">
          <label className="field">
            <span>Nom du bâtiment</span>
            <input value={buildingName} onChange={(e) => setBuildingName(e.target.value)} placeholder="ex. Bâtiment A" />
          </label>
          <label className="field">
            <span>Poussins mis en place</span>
            <input type="number" value={chicksPlaced} onChange={(e) => setChicksPlaced(e.target.value)} placeholder="500" />
          </label>
          <label className="field">
            <span>Cycle de croissance</span>
            <div className="inline-field">
              <input type="number" value={growthCycle} onChange={(e) => setGrowthCycle(e.target.value)} />
              <select value={growthCycleUnit} onChange={(e) => setGrowthCycleUnit(e.target.value)}>
                {UNITS.map((u) => (
                  <option key={u} value={u}>{UNIT_LABELS_PLURAL[u]}</option>
                ))}
              </select>
            </div>
          </label>
          <label className="field">
            <span>Nom de la bande</span>
            <input
              value={batchName}
              onChange={(e) => setBatchName(e.target.value)}
              placeholder="ex. Bande printemps 2026"
              required={mode === "onboarding"}
            />
          </label>
        </div>
      </div>

      <div className="tabs">
        {categories.map((cat) => {
          const Icon = iconFor(cat.icon);
          return (
            <button
              key={cat.id}
              className={`tab ${cat.id === activeCategoryId ? "active" : ""}`}
              onClick={() => setActiveCategoryId(cat.id)}
            >
              <Icon size={15} strokeWidth={1.8} />
              {cat.label}
              <span className="tab-count">{(schedules[cat.id] || []).length}</span>
              {mode === "management" && (
                <span
                  className="tab-delete"
                  role="button"
                  tabIndex={0}
                  aria-label={`Supprimer la catégorie ${cat.label}`}
                  onClick={(e) => { e.stopPropagation(); setConfirmDeleteCategory(cat); }}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.stopPropagation(); setConfirmDeleteCategory(cat); } }}
                >
                  <X size={12} strokeWidth={2.5} />
                </span>
              )}
            </button>
          );
        })}

        {addingCategory ? (
          <div className="tab-add-form">
            <input
              autoFocus
              value={newCategoryLabel}
              onChange={(e) => setNewCategoryLabel(e.target.value)}
              placeholder="Nom de la catégorie"
              onKeyDown={(e) => { if (e.key === "Enter") addCategory(); if (e.key === "Escape") setAddingCategory(false); }}
            />
            <div className="icon-picker">
              {ICON_OPTIONS.map(({ name, Icon }) => (
                <button
                  key={name}
                  type="button"
                  className={`icon-picker-option ${newCategoryIcon === name ? "active" : ""}`}
                  onClick={() => setNewCategoryIcon(name)}
                  aria-label={name}
                >
                  <Icon size={15} strokeWidth={1.8} />
                </button>
              ))}
            </div>
            <div className="tab-add-actions">
              <button type="button" className="icon-button" onClick={() => setAddingCategory(false)} aria-label="Annuler">
                <X size={14} strokeWidth={2} />
              </button>
              <button type="button" className="icon-button" onClick={addCategory} aria-label="Confirmer">
                <Check size={14} strokeWidth={2} />
              </button>
            </div>
            {categoryError && <p className="field-error" style={{ margin: "6px 0 0" }}>{categoryError}</p>}
          </div>
        ) : (
          <button className="tab tab-add" onClick={() => setAddingCategory(true)} type="button" aria-label="Ajouter une catégorie">
            <Plus size={15} strokeWidth={2.2} />
          </button>
        )}
      </div>

      {confirmDeleteCategory && (
        <div className="card schedule-card" style={{ marginBottom: 18, borderColor: "var(--danger)" }}>
          <p style={{ margin: "0 0 12px", fontSize: 14 }}>
            Supprimer la catégorie « {confirmDeleteCategory.label} » supprimera aussi toutes ses lignes de protocole
            ({(schedules[confirmDeleteCategory.id] || []).length} ligne(s)). Cette action est définitive. Continuer ?
          </p>
          <div style={{ display: "flex", gap: 10 }}>
            <button className="delete-button" style={{ width: "auto", padding: "0 16px" }} onClick={() => deleteCategory(confirmDeleteCategory)} disabled={categoryBusy}>
              {categoryBusy ? <Loader2 size={16} className="spin" /> : "Supprimer la catégorie"}
            </button>
            <button className="add-button" onClick={() => setConfirmDeleteCategory(null)}>Annuler</button>
          </div>
        </div>
      )}

      <div className="card schedule-card">
        <div className="table-head">
          <span>De</span>
          <span>À</span>
          <span>Action</span>
          <span>Détails</span>
          <span />
        </div>

        <div className="rows">
          {rows.map((row) => (
            <div key={row.id} className="schedule-row">
              <div className="bound-input">
                <input type="number" value={row.fromValue} onChange={(e) => updateRow(row.id, "fromValue", e.target.value)} />
                <select value={row.fromUnit} onChange={(e) => updateRow(row.id, "fromUnit", e.target.value)}>
                  {UNITS.map((u) => (
                    <option key={u} value={u}>{UNIT_LABELS[u]}</option>
                  ))}
                </select>
              </div>

              {row.untilEnd ? (
                <div className="end-cycle">
                  <span>Fin de cycle</span>
                  <button type="button" onClick={() => updateRow(row.id, "untilEnd", false)}>définir une date</button>
                </div>
              ) : (
                <div className="bound-input">
                  <input type="number" value={row.toValue} onChange={(e) => updateRow(row.id, "toValue", e.target.value)} />
                  <select value={row.toUnit} onChange={(e) => updateRow(row.id, "toUnit", e.target.value)}>
                    {UNITS.map((u) => (
                      <option key={u} value={u}>{UNIT_LABELS[u]}</option>
                    ))}
                  </select>
                </div>
              )}

              <input
                value={row.what}
                onChange={(e) => updateRow(row.id, "what", e.target.value)}
                placeholder="ex. Aliment démarrage"
              />
              <input
                value={row.details}
                onChange={(e) => updateRow(row.id, "details", e.target.value)}
                placeholder="ex. 3000 kcal, 22,5% de protéines"
              />
              <button className="delete-button" aria-label="Supprimer la ligne" onClick={() => deleteRow(row.id)}>
                <Trash2 size={16} strokeWidth={1.8} />
              </button>
            </div>
          ))}
          {rows.length === 0 && <p className="empty-state">Aucune ligne dans cette catégorie pour le moment.</p>}
        </div>

        <button className="add-button" onClick={addRow}>
          <Plus size={14} strokeWidth={2.5} />
          Ajouter une ligne
        </button>
      </div>

      <div className="save-bar">
        <span className={`save-message ${saveMessage ? "success" : ""}`}>{saveMessage}</span>
        <button className="save-button" onClick={handleSave} disabled={saving || totalRows === 0}>
          {saving ? <Loader2 size={16} className="spin" /> : mode === "onboarding" ? "Suivant" : "Enregistrer le protocole"}
        </button>
      </div>

      {helpOpen && (
        <div className="help-overlay" onClick={() => setHelpOpen(false)}>
          <div className="help-panel" onClick={(e) => e.stopPropagation()}>
            <div className="help-panel-header">
              <h2>Comment configurer le protocole</h2>
              <button className="icon-button" onClick={() => setHelpOpen(false)} aria-label="Fermer">
                <X size={16} strokeWidth={2} />
              </button>
            </div>

            <div className="help-panel-body">
              <section>
                <h3>Les colonnes</h3>
                <p><strong>De / À</strong> — la plage d'application de la ligne, en jours, semaines ou mois depuis le début de la bande (ex. « du jour 1 au jour 15 »).</p>
                <p><strong>Fin de cycle</strong> — active à la place de « À » : la ligne s'applique jusqu'à la fin de la bande plutôt qu'à une date fixe.</p>
                <p><strong>Action</strong> — le nom court de ce qui est fait (ex. « Aliment démarrage », « Maladie de Newcastle »).</p>
                <p><strong>Détails</strong> — dosage, composition ou note libre.</p>
              </section>

              <section>
                <h3>Catégories personnalisées</h3>
                <p>
                  Le bouton « + » à droite des onglets ajoute une nouvelle catégorie : donnez-lui un nom et choisissez
                  une icône dans la liste proposée. En mode gestion, elle est enregistrée immédiatement ; pendant la
                  création de la ferme, elle est ajoutée avec le reste du protocole à la fin de l'assistant.
                  Supprimer une catégorie (bouton × au survol de l'onglet, en mode gestion) supprime aussi toutes ses
                  lignes — une confirmation est toujours demandée.
                </p>
              </section>

              <section>
                <h3>Un exemple par catégorie par défaut</h3>
                <table className="help-example-table">
                  <thead>
                    <tr><th>Catégorie</th><th>De</th><th>À</th><th>Action</th><th>Détails</th></tr>
                  </thead>
                  <tbody>
                    {HELP_EXAMPLES.map((ex) => {
                      const Icon = iconFor(ex.icon);
                      return (
                        <tr key={ex.label}>
                          <td><Icon size={14} strokeWidth={1.8} style={{ marginRight: 6, verticalAlign: "-2px" }} />{ex.label}</td>
                          <td>{ex.from}</td>
                          <td>{ex.to}</td>
                          <td>{ex.what}</td>
                          <td>{ex.details}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <p className="schedule-note" style={{ marginTop: 8 }}>
                  Ces lignes sont des exemples affichés à titre indicatif — elles ne sont jamais ajoutées automatiquement
                  à votre protocole (utilisez « Charger le modèle de départ » pour cela).
                </p>
              </section>

              <a href={helpDocUrl} target="_blank" rel="noreferrer" className="help-panel-link">
                En savoir plus →
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
