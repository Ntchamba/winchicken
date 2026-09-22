import { useEffect, useRef, useState } from "react";
import {
  Wheat, Stethoscope, Wrench, Layers, Package, Syringe, Droplets, Boxes, ShoppingCart,
  Thermometer, Bug, ClipboardList, Egg, Wind, Plus, Trash2, Loader2, X, Check, RotateCcw,
} from "lucide-react";
import { stockApi } from "../api/endpoints";
import { getServerErrorMessage } from "../api/errors";
import UnitField from "./UnitField";
import { compositionByOutput } from "../utils/compositions";
import "../styles/house-protocol-theme-light.css";
import { todayISO as localTodayISO } from "../utils/localDate";
import { useTodayISO } from "../hooks/useTodayISO";

// Curated icon picker for custom stock categories — kept in sync by hand with the backend's
// STOCK_CATEGORY_ICON_CHOICES (apps/stock/models.py). The four defaults' icons are a subset.
const STOCK_ICON_OPTIONS = [
  { name: "Wheat", Icon: Wheat }, { name: "Stethoscope", Icon: Stethoscope },
  { name: "Wrench", Icon: Wrench }, { name: "Layers", Icon: Layers },
  { name: "Package", Icon: Package }, { name: "Syringe", Icon: Syringe },
  { name: "Droplets", Icon: Droplets }, { name: "Boxes", Icon: Boxes },
  { name: "ShoppingCart", Icon: ShoppingCart }, { name: "Thermometer", Icon: Thermometer },
  { name: "Bug", Icon: Bug }, { name: "ClipboardList", Icon: ClipboardList },
  { name: "Egg", Icon: Egg }, { name: "Wind", Icon: Wind },
];
const ICON_MAP = Object.fromEntries(STOCK_ICON_OPTIONS.map((o) => [o.name, o.Icon]));
export const stockIconFor = (name) => ICON_MAP[name] || Package;

// feed_stage: internal values stay English (backend FeedStage enum); French labels shown.
const FEED_STAGE_OPTIONS = [
  { value: "STARTER", label: "Démarrage" },
  { value: "GROWER", label: "Croissance" },
  { value: "FINISHER", label: "Finition" },
  { value: "PULLET_STAGE", label: "Poulette" },
  { value: "LAYER_STAGE", label: "Pondeuse" },
  { value: "NOT_APPLICABLE", label: "Non applicable" },
];


const todayISO = () => localTodayISO();

// Suggested article types for the free-text "Détail" combobox on non-feed/non-vet categories.
// The user may type anything; these just prime the datalist. They also steer which finance
// category a stock purchase is filed under (see apps/stock/purchasing.py _expense_category_for).
const STOCK_ITEM_TYPE_OPTIONS = [
  "Aliment / Provende",
  "Médicament / Vaccin",
  "Équipement / Matériel",
  "Litière / Consommable",
  "Objet divers",
];

// Column widths for the item table — Article | Détail | Seuil | Prix | Fournisseur | Quantité |
// Date | (delete). Set inline on .table-head and every .schedule-row because the shared grid in
// house-protocol-theme-light.css only declares 5 tracks.
const ITEM_GRID = "1.4fr 1fr 1.1fr .7fr 1.1fr .8fr 140px 34px";

let nextRowId = 1000;
const makeRow = (overrides = {}) => ({
  id: nextRowId++,
  itemCode: null,
  item: "",
  feedStage: "STARTER",
  coldChain: false,
  threshold: 0,
  unit: "kg",
  price: 0,
  supplier: null,
  itemType: "",
  quantity: "",
  originalQuantity: 0,
  date: todayISO(),
  ...overrides,
});

/**
 * Stock parameters editor — dynamic category tabs (the four per-farm defaults +
 * any custom ones added via "+"), each a table of StockItem-shaped rows. Used for onboarding
 * step 2 and, from /dashboard/stock, inside the "Mettre à jour le stock" modal.
 *
 * Categories come from the backend (`GET /api/farms/{farmId}/stock-categories/`) — the farm
 * already exists in both contexts, so add/delete persist immediately (optimistic), mirroring
 * `HouseProtocolForm`'s management-mode behaviour. `kind` drives the per-row "Détail" cell:
 * FEED → feed-stage select, VETERINARY → cold-chain toggle, everything else → no detail.
 *
 * @param {Object} initialData - `{ [categoryId]: [row, ...] }`, row =
 *   `{ id, itemCode?, item, feedStage, coldChain, threshold, unit, price, supplier }`.
 * @param {Object[]} initialCategories - `[{ id, label, icon, kind }]` in display order.
 * @param {Object[]} [initialSuppliers] - `[{ id, name }]` for the per-row supplier dropdown.
 * @param {number} [farmId] - enables live category/supplier writes; omit for the read-only demo.
 * @param {Object} [warehouse] - display-only header seed `{ name, leadTime, leadTimeUnit }`. No
 *   currency: FCFA (XAF) is an architecture decision of this app, not a per-farm setting — the
 *   selector that used to sit here was never persisted anywhere and `utils/money.js` prints FCFA
 *   regardless, so picking EUR changed nothing but lied on every screen (FIX 5).
 * @param {"onboarding"|"management"} [mode]
 * @param {boolean} [saving]
 * @param {(payload) => Promise<void>} [onSave] - payload.items entries match StockItemSerializer
 *   field names (item_code, category, name, unit, feed_stage, cold_chain_required,
 *   alert_threshold, unit_price, supplier).
 * @param {() => void} [onBack] - onboarding only.
 * @param {() => void} [onSuppliersChanged] - called after an inline "+ Nouveau fournisseur".
 * @param {boolean} [showStockEntry] - show the "Quantité" + "Date" columns (the "Mettre à jour
 *   le stock" modal only); each row's quantity is recorded as a stock IN movement on save.
 */
export default function StockParametersForm({
  initialData = {},
  initialCategories = [],
  initialSuppliers = [],
  farmId = null,
  warehouse = {},
  mode = "management",
  saving = false,
  onSave,
  onBack,
  onSuppliersChanged,
  showStockEntry = false,
  compositions = [],
}) {
  const composed = compositionByOutput(compositions);
  const [deductComposed, setDeductComposed] = useState(true);
  const [warehouseName, setWarehouseName] = useState(warehouse.name || "Entrepôt principal");
  const [leadTime, setLeadTime] = useState(warehouse.leadTime ?? 3);
  const [leadTimeUnit, setLeadTimeUnit] = useState(warehouse.leadTimeUnit || "Days");

  const [categories, setCategories] = useState(initialCategories);
  const [activeCategoryId, setActiveCategoryId] = useState(initialCategories[0]?.id ?? null);
  const [data, setData] = useState(initialData);
  const [suppliers, setSuppliers] = useState(initialSuppliers);
  const [saveMessage, setSaveMessage] = useState("");
  // Same reason as HouseProtocolForm's (FIX 8, group 3): a rejected save left the onboarding
  // step sitting there with no message at all, indistinguishable from a click that missed.
  const [saveError, setSaveError] = useState("");

  const [addingCategory, setAddingCategory] = useState(false);
  const [newCategoryLabel, setNewCategoryLabel] = useState("");
  const [newCategoryIcon, setNewCategoryIcon] = useState(STOCK_ICON_OPTIONS[0].name);
  const [categoryError, setCategoryError] = useState("");
  const [categoryBusy, setCategoryBusy] = useState(false);
  const [confirmDeleteCategory, setConfirmDeleteCategory] = useState(null);

  const [addingSupplierForRow, setAddingSupplierForRow] = useState(null);
  const [newSupplierName, setNewSupplierName] = useState("");
  const [supplierBusy, setSupplierBusy] = useState(false);
  const [supplierError, setSupplierError] = useState("");
  // Re-entrancy guard, not `supplierBusy`: the inline name field confirms on both Enter
  // and the check button, and a React state flag only blocks the second call once the
  // update has flushed (see the cashier double-submit incident).
  const supplierInFlight = useRef(false);

  // Each row carries its own "Date" cell, seeded with the local day the rows were built
  // (`buildStockRows`) or the row was added (`makeRow`). This screen is one a worker leaves
  // open, so that seed goes stale across local midnight and the opening-stock IN movement gets
  // filed against yesterday. Roll every cell that still shows the previous today forward, and
  // leave a date the user picked on purpose alone — `useDateDefaultingToToday`'s rule, applied
  // across a table of rows instead of a single field.
  const today = useTodayISO();
  const previousTodayRef = useRef(today);

  useEffect(() => {
    // Read the ref into a local *before* scheduling: a functional updater runs during the next
    // render, so one reading `previousTodayRef.current` would see the line below, never the
    // previous day. (Keeping it pure also survives StrictMode's double invocation.)
    const previousToday = previousTodayRef.current;
    if (previousToday === today) return;
    previousTodayRef.current = today;

    setData((prev) => {
      let changed = false;
      const next = {};
      for (const [categoryId, categoryRows] of Object.entries(prev)) {
        next[categoryId] = categoryRows.map((row) => {
          if (row.date !== previousToday) return row;
          changed = true;
          return { ...row, date: today };
        });
      }
      return changed ? next : prev;
    });
  }, [today]);

  const activeCategory = categories.find((c) => c.id === activeCategoryId) || null;
  const rows = data[activeCategoryId] || [];
  const totalItems = Object.values(data).reduce((sum, arr) => sum + arr.length, 0);
  const hasComposedRow = Object.values(data).some((arr) => arr.some((r) => composed[r.itemCode]));

  const updateRow = (rowId, field, value) => {
    setData((prev) => ({
      ...prev,
      [activeCategoryId]: (prev[activeCategoryId] || []).map((r) => (r.id === rowId ? { ...r, [field]: value } : r)),
    }));
  };

  const addRow = () => {
    setData((prev) => ({ ...prev, [activeCategoryId]: [...(prev[activeCategoryId] || []), makeRow()] }));
  };

  const deleteRow = (rowId) => {
    setData((prev) => ({ ...prev, [activeCategoryId]: (prev[activeCategoryId] || []).filter((r) => r.id !== rowId) }));
  };

  const resetForm = () => {
    setData(initialData);
    setCategories(initialCategories);
    setActiveCategoryId(initialCategories[0]?.id ?? null);
    setSaveMessage("");
  };

  const addCategory = async () => {
    const label = newCategoryLabel.trim();
    if (!label) {
      setCategoryError("Le nom de la catégorie est requis.");
      return;
    }
    setCategoryError("");
    const tempId = `pending-${Date.now()}`;
    setCategories((prev) => [...prev, { id: tempId, label, icon: newCategoryIcon, kind: "CUSTOM" }]);
    setActiveCategoryId(tempId);
    setAddingCategory(false);
    setNewCategoryLabel("");
    setNewCategoryIcon(STOCK_ICON_OPTIONS[0].name);

    if (!farmId) return;
    try {
      const { data: created } = await stockApi.addCategory(farmId, { label, icon: newCategoryIcon });
      setCategories((prev) => prev.map((c) => (c.id === tempId ? created : c)));
      setActiveCategoryId((cur) => (cur === tempId ? created.id : cur));
      setData((prev) => ({ ...prev, [created.id]: prev[tempId] || [] }));
    } catch (err) {
      setCategories((prev) => prev.filter((c) => c.id !== tempId));
      setActiveCategoryId((cur) => (cur === tempId ? categories[0]?.id : cur));
      setCategoryError(getServerErrorMessage(err, "Impossible d'ajouter la catégorie."));
    }
  };

  const deleteCategory = async (category) => {
    setCategoryBusy(true);
    try {
      if (farmId && typeof category.id === "number") {
        await stockApi.removeCategory(category.id);
      }
      setCategories((prev) => {
        const next = prev.filter((c) => c.id !== category.id);
        setActiveCategoryId((cur) => (cur === category.id ? next[0]?.id ?? null : cur));
        return next;
      });
      setData((prev) => {
        const { [category.id]: _dropped, ...rest } = prev;
        return rest;
      });
    } catch (err) {
      // The category stays on screen on failure, which reads as "nothing happened" — say why.
      setCategoryError(getServerErrorMessage(err, "Impossible de supprimer la catégorie."));
    } finally {
      setCategoryBusy(false);
      setConfirmDeleteCategory(null);
    }
  };

  const addSupplierInline = async (rowId) => {
    const name = newSupplierName.trim();
    if (!farmId) return;
    if (!name) {
      setSupplierError("Saisissez le nom du fournisseur.");
      return;
    }
    if (supplierInFlight.current) return;
    supplierInFlight.current = true;
    setSupplierError("");
    setSupplierBusy(true);
    try {
      const { data: created } = await stockApi.addSupplier(farmId, { name });
      setSuppliers((prev) => [...prev, created]);
      updateRow(rowId, "supplier", created.id);
      setAddingSupplierForRow(null);
      setNewSupplierName("");
      onSuppliersChanged?.();
    } catch (err) {
      // The inline field stays open with the typed name intact — the only copy of it.
      setSupplierError(getServerErrorMessage(err, "Impossible d'ajouter le fournisseur."));
    } finally {
      supplierInFlight.current = false;
      setSupplierBusy(false);
    }
  };

  const buildPayload = () => ({
    warehouseName,
    leadTime,
    leadTimeUnit,
    items: categories.flatMap((cat) =>
      (data[cat.id] || []).map((row) => ({
        item_code: row.itemCode || undefined,
        category: typeof cat.id === "number" ? cat.id : undefined,
        name: row.item,
        unit: row.unit,
        feed_stage: cat.kind === "FEED" ? row.feedStage : "NOT_APPLICABLE",
        cold_chain_required: cat.kind === "VETERINARY" ? !!row.coldChain : false,
        alert_threshold: Number(row.threshold) || 0,
        unit_price: Number(row.price) || 0,
        supplier: row.supplier ?? null,
        // Free-text article type (feed/vet rows keep it blank — their kind already says what
        // they are). Persisted by PUT and used to file an auto-recorded purchase under the
        // right finance category.
        item_type: cat.kind === "FEED" || cat.kind === "VETERINARY" ? "" : (row.itemType || ""),
        // Quantité / Date columns — ignored by PUT /stock-items/, read by
        // StockParametersModal.handleSave to record a stock IN movement (and, for a brand-new
        // article with a unit price, the matching purchase in Finances).
        quantity: row.quantity === "" || row.quantity == null ? null : Number(row.quantity),
        movement_date: row.date || todayISO(),
        is_new_item: !row.itemCode,
        // For a composed item whose level is raised here: the on-hand at load time and whether
        // the delta should be treated as a production run (deduct the recipe ingredients).
        original_quantity: Number(row.originalQuantity) || 0,
        deduct_production: !!(deductComposed && composed[row.itemCode]),
      }))
    ),
  });

  const handleSave = async () => {
    if (!onSave || saving) return;
    setSaveError("");
    try {
      await onSave(buildPayload());
      if (mode !== "onboarding") {
        setSaveMessage("Enregistré");
        setTimeout(() => setSaveMessage(""), 3000);
      }
    } catch (err) {
      setSaveError(getServerErrorMessage(err, "Les paramètres n'ont pas été enregistrés. Réessayez."));
    }
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
          Définissez les seuils d'alerte, les unités, les prix et le fournisseur par défaut de chaque article.
          Ajoutez vos propres catégories avec le bouton « + ».
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
        {categories.map((cat) => {
          const Icon = stockIconFor(cat.icon);
          return (
            <button
              key={cat.id}
              className={`tab ${cat.id === activeCategoryId ? "active" : ""}`}
              onClick={() => setActiveCategoryId(cat.id)}
              type="button"
            >
              <Icon size={15} strokeWidth={1.8} />
              {cat.label}
              <span className="tab-count">{(data[cat.id] || []).length}</span>
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
              {STOCK_ICON_OPTIONS.map(({ name, Icon }) => (
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
            Supprimer la catégorie « {confirmDeleteCategory.label} » supprimera aussi tous ses articles
            ({(data[confirmDeleteCategory.id] || []).length} article(s)). Cette action est définitive. Continuer ?
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
        <div className="schedule-heading">
          <div>
            <span className="section-kicker">CATÉGORIE</span>
            <h2>{activeCategory?.label || "—"}</h2>
          </div>
        </div>

        <div className="table-head" style={showStockEntry ? { gridTemplateColumns: ITEM_GRID } : undefined}>
          <span>Article</span>
          <span>Détail</span>
          <span>Seuil d'alerte</span>
          <span>Prix unitaire</span>
          <span>Fournisseur</span>
          {showStockEntry && <span>Quantité</span>}
          {showStockEntry && <span>Date</span>}
          <span />
        </div>

        <datalist id="stock-item-type-options">
          {STOCK_ITEM_TYPE_OPTIONS.map((t) => <option key={t} value={t} />)}
        </datalist>

        <div className="rows">
          {rows.map((row) => (
            <div key={row.id} className="schedule-row" style={showStockEntry ? { gridTemplateColumns: ITEM_GRID } : undefined}>
              <input
                value={row.item}
                onChange={(e) => updateRow(row.id, "item", e.target.value)}
                placeholder="Nom de l'article"
              />

              {activeCategory?.kind === "FEED" ? (
                <select value={row.feedStage} onChange={(e) => updateRow(row.id, "feedStage", e.target.value)}>
                  {FEED_STAGE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              ) : activeCategory?.kind === "VETERINARY" ? (
                <select
                  value={row.coldChain ? "yes" : "no"}
                  onChange={(e) => updateRow(row.id, "coldChain", e.target.value === "yes")}
                >
                  <option value="no">Chaîne du froid : Non</option>
                  <option value="yes">Chaîne du froid : Oui</option>
                </select>
              ) : (
                <input
                  list="stock-item-type-options"
                  value={row.itemType || ""}
                  onChange={(e) => updateRow(row.id, "itemType", e.target.value)}
                  placeholder="Type (ex. Équipement, Objet…)"
                  aria-label="Type d'article"
                />
              )}

              <div className="bound-input">
                <input
                  type="number"
                  value={row.threshold}
                  onChange={(e) => updateRow(row.id, "threshold", e.target.value)}
                />
                <UnitField value={row.unit} onChange={(u) => updateRow(row.id, "unit", u)} />
              </div>

              <input
                value={row.price}
                onChange={(e) => updateRow(row.id, "price", e.target.value)}
                placeholder="Prix unitaire"
              />

              {addingSupplierForRow === row.id ? (
                <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
                  <input
                    autoFocus
                    value={newSupplierName}
                    onChange={(e) => setNewSupplierName(e.target.value)}
                    placeholder="Nom du fournisseur"
                    onKeyDown={(e) => { if (e.key === "Enter") addSupplierInline(row.id); if (e.key === "Escape") setAddingSupplierForRow(null); }}
                  />
                  <button type="button" className="icon-button" onClick={() => addSupplierInline(row.id)} aria-label="Confirmer" disabled={supplierBusy}>
                    <Check size={13} strokeWidth={2.2} />
                  </button>
                  <button
                    type="button"
                    className="icon-button"
                    onClick={() => { setAddingSupplierForRow(null); setSupplierError(""); }}
                    aria-label="Annuler"
                  >
                    <X size={13} strokeWidth={2.2} />
                  </button>
                  {supplierError && <span className="field-error">{supplierError}</span>}
                </span>
              ) : (
                <select
                  value={row.supplier ?? ""}
                  onChange={(e) => {
                    if (e.target.value === "__new__") { setNewSupplierName(""); setAddingSupplierForRow(row.id); return; }
                    updateRow(row.id, "supplier", e.target.value ? Number(e.target.value) : null);
                  }}
                >
                  <option value="">Aucun</option>
                  {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                  {farmId && <option value="__new__">+ Nouveau fournisseur</option>}
                </select>
              )}

              {showStockEntry && (
                <input
                  type="number"
                  min="0"
                  step="any"
                  placeholder="Quantité"
                  aria-label="Quantité en stock"
                  value={row.quantity}
                  onChange={(e) => updateRow(row.id, "quantity", e.target.value)}
                />
              )}
              {showStockEntry && (
                <input
                  type="date"
                  aria-label="Date"
                  value={row.date}
                  onChange={(e) => updateRow(row.id, "date", e.target.value)}
                />
              )}

              <button className="delete-button" aria-label="Supprimer l'article" onClick={() => deleteRow(row.id)}>
                <Trash2 size={16} strokeWidth={1.8} />
              </button>
            </div>
          ))}
          {rows.length === 0 && <p className="empty-state">Aucun article dans cette catégorie pour le moment.</p>}
        </div>

        <button className="add-button" onClick={addRow} type="button">
          <Plus size={14} strokeWidth={2.5} />
          Ajouter un article
        </button>
      </div>

      {showStockEntry && hasComposedRow && (
        <label className="schedule-note" style={{ display: "flex", alignItems: "center", gap: 8, margin: "10px 0 0" }}>
          <input
            type="checkbox"
            checked={deductComposed}
            onChange={(e) => setDeductComposed(e.target.checked)}
          />
          Décompter les ingrédients des articles composés dont j'augmente le stock (comme une exécution)
        </label>
      )}

      {mode === "onboarding" ? (
        <div className="save-bar">
          {onBack && (
            <button className="add-button" onClick={onBack} disabled={saving}>Retour</button>
          )}
          <span className="save-message error" role="alert" style={{ flex: 1 }}>{saveError}</span>
          <button className="save-button" onClick={handleSave} disabled={saving || totalItems === 0}>
            {saving ? <Loader2 size={16} className="spin" /> : "Suivant"}
          </button>
        </div>
      ) : (
        <div className="save-bar">
          <span
            className={`save-message ${saveError ? "error" : saveMessage ? "success" : ""}`}
            role={saveError ? "alert" : undefined}
          >
            {saveError || saveMessage}
          </span>
          <button className="add-button" style={{ marginTop: 0 }} onClick={resetForm} disabled={saving} type="button">
            <RotateCcw size={14} strokeWidth={2.2} />
            Réinitialiser
          </button>
          <button className="save-button" onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 size={16} className="spin" /> : "Enregistrer les paramètres"}
          </button>
        </div>
      )}
    </div>
  );
}
