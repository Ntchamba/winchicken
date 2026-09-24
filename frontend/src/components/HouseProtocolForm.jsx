import { useEffect, useRef, useState } from "react";
import {
  Soup, Plus, Trash2, Loader2, Sparkles, HelpCircle, X, Check, Info,
  FileSpreadsheet, Download,
} from "lucide-react";
import { housesApi, protocolImportApi, stockApi } from "../api/endpoints";
import { getServerErrorMessage } from "../api/errors";
import ConfirmDialog from "./ConfirmDialog";
import ResourceCombobox from "./ResourceCombobox";
import UnitField from "./UnitField";
import { DEFAULT_CATEGORIES, ICON_OPTIONS, iconFor, makeRow, nextRowId } from "../utils/protocolRows";
import { resolveProtocolImportRows } from "../utils/protocolImportResolve";
import "../styles/house-protocol-theme-light.css";

// Re-exported from its own module (utils/protocolRows) since 2026-09-11 — the onboarding
// Excel-import screen shares the same row factory. Kept exported here so the five existing
// `import { iconFor } from ".../HouseProtocolForm"` call sites stay untouched.
export { iconFor };

// Stable identity for the `stockItems` default — an inline `[]` in the destructure is a fresh
// array every render, which makes the `setStockItemList(stockItems)` effect below re-fire on
// every render and spin into "Maximum update depth exceeded" for the callers that don't pass
// the prop (onboarding + management protocol pages). Same pattern as OnboardingContext's EMPTY_STOCK.
const EMPTY_STOCK_ITEMS = [];

// Internal values stay English to match ProtocolUnit (backend enum) — .toUpperCase()
// on these feeds `from_unit`/`to_unit` directly. Display labels are French, separately.
const UNITS = ["Day", "Week", "Month"];
const UNIT_LABELS = { Day: "Jour", Week: "Semaine", Month: "Mois" };
const UNIT_LABELS_PLURAL = { Day: "Jours", Week: "Semaines", Month: "Mois" };
const UNIT_TO_DAYS = { Day: 1, Week: 7, Month: 30 };

// The stock-consumption fields of one protocol-line payload, from a row's dosage mode.
// Mirrors ProtocolTemplateSerializer.validate: at most one of the two amounts is non-null.
const consumptionFields = (row) => {
  const amount = row.consumptionMode === "dose" ? row.dosePerBird : row.quantityPerDay;
  const value = !row.stockItemCode || amount === "" || amount == null ? null : Number(amount);
  return {
    stock_item: row.stockItemCode || null,
    quantity_per_day: row.consumptionMode === "dose" ? null : value,
    dose_per_bird: row.consumptionMode === "dose" ? value : null,
  };
};

function formatSlotTime(value) {
  // Backend TimeField values come back "HH:MM:SS" (DRF's default TimeField output); <input
  // type="time"> and the "07h00–09h00" chip label both only ever want "HH:MM".
  return typeof value === "string" ? value.slice(0, 5) : value;
}

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
 * 7.3 "no default data" rule; see root README.md "Autonomous decisions" for why this button
 * exists instead of auto-loading).
 *
 * @param {Object} [initialHeader] - `{ buildingName, chicksPlaced, growthCycle, growthCycleUnit, batchName, weighingFrequency }`
 *   seed values for the house/batch header fields. `weighingFrequency` (2026-08-25) is
 *   `"DAY"|"WEEK"|"MONTH"|""` — optional, drives a recurring weighing reminder
 *   (`AlertRule`), never restricts when a weight can actually be logged via quick-entry.
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
 * @param {string} [submitLabel] - Overrides the default save-button text ("Suivant" in
 *   onboarding mode, "Enregistrer le protocole" in management mode) — 2026-08-27, for the
 *   "+ Nouvelle bande" add-a-house flow, where "Suivant" was misleading (this button returns
 *   straight to the dashboard, there is no next wizard step to go to).
 * @param {(payload: object) => Promise<void>} [onAddAnother] - 2026-08-27, multi-batch
 *   first-time onboarding: when provided, renders a second button that submits the current
 *   house via the same payload shape as `onSave` but *doesn't* advance the wizard — the caller
 *   is expected to reset `initialHeader`/`initialCategories`/`initialSchedules` (via a changed
 *   `key`, so this component actually remounts with fresh state) so the form is ready for
 *   another house. Onboarding mode only; unused/omit everywhere else, including the
 *   "+ Nouvelle bande" single-house add flow.
 */
export default function HouseProtocolForm({
  initialHeader = {},
  initialCategories = null,
  initialSchedules = {},
  mode = "management",
  houseCode = null,
  saving = false,
  onSave,
  onAddAnother,
  helpDocUrl = "/docs/protocol-configuration.md",
  submitLabel,
  stockItems = EMPTY_STOCK_ITEMS,
  farmId = null,
  // false = this house has no active batch (management/edit-modal only): the batch-scoped
  // fields below can't be persisted, so they're disabled and a notice explains why.
  batchEditable = true,
}) {
  // Local mirror of `stockItems` so an item created inline from the Consommation selector
  // (ResourceCombobox "+ Créer …") shows up immediately without a prop round-trip.
  const [stockItemList, setStockItemList] = useState(stockItems);
  const [createdInlineCodes, setCreatedInlineCodes] = useState(() => new Set());
  useEffect(() => { setStockItemList(stockItems); }, [stockItems]);

  const [buildingName, setBuildingName] = useState(initialHeader.buildingName || "");
  const [chicksPlaced, setChicksPlaced] = useState(initialHeader.chicksPlaced || "");
  const [growthCycle, setGrowthCycle] = useState(initialHeader.growthCycle || 56);
  const [growthCycleUnit, setGrowthCycleUnit] = useState(initialHeader.growthCycleUnit || "Day");
  const [batchName, setBatchName] = useState(initialHeader.batchName || "");
  const [batchNameTouched, setBatchNameTouched] = useState(false);
  const [weighingFrequency, setWeighingFrequency] = useState(initialHeader.weighingFrequency || "");
  const [categories, setCategories] = useState(initialCategories || DEFAULT_CATEGORIES);
  const [activeCategoryId, setActiveCategoryId] = useState((initialCategories || DEFAULT_CATEGORIES)[0]?.id);
  const [schedules, setSchedules] = useState(initialSchedules);

  // Inline creation of a StockItem — from a protocol row's "Ressource" combobox (category
  // defaulted from the active row's protocol category) or from the Excel import (category
  // defaulted from that row's own Catégorie). `category_hint` → StockCategory.kind server-side.
  const createStockItem = async (name, categoryLabel, unit) => {
    const hint = categoryLabel || categories.find((c) => c.id === activeCategoryId)?.label;
    const { data, status } = await stockApi.addItem(farmId, { name, unit: unit || "kg", category_hint: hint });
    setStockItemList((prev) => (prev.some((s) => s.item_code === data.item_code) ? prev : [...prev, data]));
    // 200 = the farm already had an article of that name and the server returned it: it is not
    // this form's to re-unit (the inline unit selector would rewrite an article already in use).
    if (status === 201) setCreatedInlineCodes((prev) => new Set(prev).add(data.item_code));
    return data;
  };

  const setStockItemUnit = (code, unit) => {
    setStockItemList((prev) => prev.map((s) => (s.item_code === code ? { ...s, unit } : s)));
    if (farmId) stockApi.updateItem(code, { unit }).catch(() => {});
  };
  const [saveMessage, setSaveMessage] = useState("");
  // A rejected save used to escape as an unhandled promise rejection from `handleSave`: the
  // wizard simply did not advance and said nothing, which is the worst possible outcome for
  // the one screen where the user has just typed a whole protocol (FIX 8, group 3).
  const [saveError, setSaveError] = useState("");
  const [helpOpen, setHelpOpen] = useState(false);

  // Excel import (docs/excel-import.md) — parse server-side, then REPLACE the form's rows with
  // the file's content (full replacement, not append). Destructive → a confirm step first.
  const importInputRef = useRef(null);
  const [importConfirmOpen, setImportConfirmOpen] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null); // { imported, skipped: [{line, reason}], replaced }
  const [importError, setImportError] = useState("");

  const [addingCategory, setAddingCategory] = useState(false);
  const [newCategoryLabel, setNewCategoryLabel] = useState("");
  const [newCategoryIcon, setNewCategoryIcon] = useState(ICON_OPTIONS[0].name);
  const [categoryError, setCategoryError] = useState("");
  // Same reason as StockParametersForm's: `categoryError` only renders inside the "ajouter une
  // catégorie" branch, so the delete path needs its own state with a reachable render site.
  const [categoryDeleteError, setCategoryDeleteError] = useState("");
  const [categoryBusy, setCategoryBusy] = useState(false);
  const [confirmDeleteCategory, setConfirmDeleteCategory] = useState(null);

  const [addingSlotForRow, setAddingSlotForRow] = useState(null);
  const [slotStart, setSlotStart] = useState("");
  const [slotEnd, setSlotEnd] = useState("");
  const [slotError, setSlotError] = useState("");

  const rows = schedules[activeCategoryId] || [];
  const totalRows = Object.values(schedules).reduce((sum, arr) => sum + arr.length, 0);
  // A batch is created in onboarding mode -> its name is required (server rejects blank too).
  const batchNameMissing = mode === "onboarding" && !batchName.trim();

  const updateRow = (rowId, field, value) => {
    setSchedules((prev) => ({
      ...prev,
      [activeCategoryId]: (prev[activeCategoryId] || []).map((r) => (r.id === rowId ? { ...r, [field]: value } : r)),
    }));
  };

  // Row day-span in days: `to - from + 1`, or `growthCycle - from + 1` for until-end rows.
  const rowSpanDays = (row) => {
    const fromDay = (Number(row.fromValue) || 0) * (UNIT_TO_DAYS[row.fromUnit] || 1);
    const cycleDays = (Number(growthCycle) || 0) * (UNIT_TO_DAYS[growthCycleUnit] || 1);
    const toDay = row.untilEnd
      ? Math.max(fromDay, cycleDays)
      : (Number(row.toValue) || 0) * (UNIT_TO_DAYS[row.toUnit] || 1);
    return Math.max(1, toDay - fromDay + 1);
  };

  // Inline, non-blocking "stock insuffisant" check (spec Part E.3). Called on change of the
  // linked item / quantity-per-day; clears when either is unset.
  const checkCoverage = async (rowId, next) => {
    const row = { ...rows.find((r) => r.id === rowId), ...next };
    const isDose = row.consumptionMode === "dose";
    const amount = isDose ? row.dosePerBird : row.quantityPerDay;
    if (!row.stockItemCode || amount === "" || amount == null) {
      updateRow(rowId, "coverageWarning", "");
      return;
    }
    try {
      const params = { days: rowSpanDays(row) };
      if (isDose) params.dose_per_bird = Number(amount);
      else params.quantity_per_day = Number(amount);
      const { data } = await stockApi.coverage(row.stockItemCode, params);
      if (data.sufficient) {
        updateRow(rowId, "coverageWarning", "");
      } else {
        const item = stockItemList.find((s) => s.item_code === row.stockItemCode);
        updateRow(
          rowId,
          "coverageWarning",
          `Stock insuffisant : à ce rythme, ${item?.name || "cet article"} sera épuisé avant la fin de cette période — ` +
            `${data.daysRemaining ?? 0} jour(s) de stock restant(s) pour ${data.daysNeeded} jour(s) prévu(s).`
        );
      }
    } catch {
      updateRow(rowId, "coverageWarning", "");
    }
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

  // Parse an uploaded .xlsx server-side, then merge every returned row into the form —
  // auto-creating any category / stock item it names via the same flows the "+" button and
  // the resource combobox use. Existing rows are kept; the user reviews everything before save.
  const handleImportFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // let the same file be picked again
    if (!file) return;

    setImporting(true);
    setImportError("");
    setImportResult(null);
    try {
      const { data } = await protocolImportApi.parse(file);

      // Category/stock-item resolution + row building is shared with the onboarding Excel
      // screen — see utils/protocolImportResolve.js.
      const { schedules: next, firstCategoryId } = await resolveProtocolImportRows(data, {
        categories,
        stockItemList,
        farmId,
        createCategory,
        createStockItem,
        // Lines the file repeats keep their server id, so saving updates them in place and
        // their task completions survive the re-import.
        existingSchedules: schedules,
      });

      // A file with no usable row must not silently wipe the whole protocol — report the
      // skipped rows and keep what's there. (The user was already warned this is a full
      // replacement; this only guards an accidental total erase from a malformed file.)
      if (next === null) {
        setImportResult({ imported: 0, skipped: data.skipped, warnings: data.warnings || [] });
        return;
      }

      // FULL REPLACEMENT (not append): the protocol becomes exactly the file's rows. The
      // normal save then does the transactional DB replace + AlertRule regeneration (past
      // Alert/SmsMessage history is preserved) via PUT /houses/{code}/protocol/. Unit is
      // always "Day" — see the note by the import button.
      setSchedules(next);
      if (firstCategoryId != null) setActiveCategoryId(firstCategoryId);
      setImportResult({ imported: data.imported, skipped: data.skipped, warnings: data.warnings || [], replaced: true });
    } catch (err) {
      // createCategory/createStockItem throw a plain Error with a ready message; the parse
      // request throws an axios error → route it through the shared parser.
      setImportError(
        err?.isAxiosError
          ? getServerErrorMessage(err, "Échec de l'import du fichier Excel.")
          : err?.message || "Échec de l'import du fichier Excel.",
      );
    } finally {
      setImporting(false);
    }
  };

  const openAddSlot = (rowId) => {
    setAddingSlotForRow(rowId);
    setSlotStart("");
    setSlotEnd("");
    setSlotError("");
  };

  const confirmAddSlot = (rowId) => {
    if (!slotStart || !slotEnd) {
      setSlotError("Les deux heures sont requises.");
      return;
    }
    if (slotEnd <= slotStart) {
      setSlotError("L'heure de fin doit être après l'heure de début.");
      return;
    }
    const row = rows.find((r) => r.id === rowId);
    updateRow(rowId, "timeSlots", [...(row?.timeSlots || []), { id: nextRowId(), startTime: slotStart, endTime: slotEnd }]);
    setAddingSlotForRow(null);
  };

  const removeTimeSlot = (rowId, slotId) => {
    const row = rows.find((r) => r.id === rowId);
    updateRow(rowId, "timeSlots", (row?.timeSlots || []).filter((s) => s.id !== slotId));
  };

  // Add a category the same way the "+" button does — optimistic local add, then persist in
  // management mode. Returns the resolved category `{ id, label, icon }` (with its real id
  // once persisted). Shared by the "+" flow and the Excel import's auto-create.
  const createCategory = async (label, icon = ICON_OPTIONS[0].name) => {
    const tempId = `pending-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    const local = { id: tempId, label, icon };
    setCategories((prev) => [...prev, local]);

    if (mode !== "management" || !houseCode) return local;
    try {
      const { data } = await housesApi.addProtocolCategory(houseCode, { label, icon });
      setCategories((prev) => prev.map((c) => (c.id === tempId ? data : c)));
      setActiveCategoryId((cur) => (cur === tempId ? data.id : cur));
      return data;
    } catch (err) {
      setCategories((prev) => prev.filter((c) => c.id !== tempId));
      throw new Error(getServerErrorMessage(err, "Impossible d'ajouter la catégorie."));
    }
  };

  const addCategory = async () => {
    const label = newCategoryLabel.trim();
    if (!label) {
      setCategoryError("Le nom de la catégorie est requis.");
      return;
    }
    setCategoryError("");
    setAddingCategory(false);
    setNewCategoryLabel("");
    const icon = newCategoryIcon;
    setNewCategoryIcon(ICON_OPTIONS[0].name);
    try {
      const created = await createCategory(label, icon);
      setActiveCategoryId(created.id);
    } catch (err) {
      setActiveCategoryId((cur) => cur);
      setCategoryError(err.message);
    }
  };

  const deleteCategory = async (category) => {
    if (categoryBusy) return;
    setCategoryDeleteError("");
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
      setConfirmDeleteCategory(null);
    } catch (err) {
      // Dialog stays open with the reason — the tab staying put on its own reads as a delete
      // that never registered.
      setCategoryDeleteError(getServerErrorMessage(err, "Impossible de supprimer la catégorie."));
    } finally {
      setCategoryBusy(false);
    }
  };

  const buildPayload = () => {
    const house = { buildingName, chicksPlaced: Number(chicksPlaced) || 0, growthCycle: Number(growthCycle) || 0, growthCycleUnit };
    if (mode === "onboarding") {
      return {
        house,
        batchName,
        weighingFrequency: weighingFrequency || null,
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
            time_slots: (row.timeSlots || []).map((s) => ({ start_time: s.startTime, end_time: s.endTime })),
            ...consumptionFields(row),
          }))
        ),
      };
    }
    return {
      house,
      batchName,
      weighingFrequency: weighingFrequency || null,
      protocolLines: categories.flatMap((cat) =>
        (schedules[cat.id] || []).map((row) => ({
          // The line's database id, so the PUT updates it in place rather than deleting and
          // recreating it — a recreate takes its completion history with it (FIX 3.5, bug A).
          // Absent on a row the user just added, which is what tells the backend to create it.
          // `row.id` is a local counter value and must never be sent: it can collide with a
          // real id and would edit an unrelated line.
          ...(row.serverId ? { id: row.serverId } : {}),
          category: cat.id,
          from_value: Number(row.fromValue) || 0,
          from_unit: row.fromUnit.toUpperCase(),
          to_value: row.untilEnd ? null : Number(row.toValue) || 0,
          to_unit: row.toUnit.toUpperCase(),
          until_end: row.untilEnd,
          what: row.what,
          details: row.details,
          time_slots: (row.timeSlots || []).map((s) => ({ start_time: s.startTime, end_time: s.endTime })),
          ...consumptionFields(row),
        }))
      ),
    };
  };

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
      // Everything typed stays on screen: this form holds a whole protocol, and re-entering it
      // because the save was silent is how a house ends up with half a protocol.
      setSaveError(getServerErrorMessage(err, "Le protocole n'a pas été enregistré. Réessayez."));
    }
  };

  const handleAddAnother = async () => {
    if (!onAddAnother || saving) return;
    setSaveError("");
    try {
      await onAddAnother(buildPayload());
    } catch (err) {
      // Same treatment as handleSave: this one submits a house *and* keeps the wizard open,
      // so a silent failure looks exactly like a house that was added.
      setSaveError(getServerErrorMessage(err, "Le bâtiment n'a pas été ajouté. Réessayez."));
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
            <span className="house-chip">BANDE</span>
            <h1 style={{ margin: "7px 0 0", fontFamily: "'Space Grotesk',sans-serif", fontSize: 22, letterSpacing: "-.03em" }}>
              {batchName || "Nouvelle bande"}
            </h1>
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
              <button className="add-button" style={{ marginTop: 0 }} onClick={loadStarterTemplate} disabled={saving}>
                <Sparkles size={14} strokeWidth={2.2} />
                Charger le modèle de départ
              </button>
              <a
                className="add-button"
                style={{ marginTop: 0, textDecoration: "none" }}
                href={protocolImportApi?.templateUrl}
              >
                <Download size={14} strokeWidth={2.2} />
                Télécharger un modèle
              </a>
              <button
                className="add-button"
                style={{ marginTop: 0 }}
                onClick={() => setImportConfirmOpen(true)}
                disabled={saving || importing}
              >
                {importing ? <Loader2 size={14} className="spin" /> : <FileSpreadsheet size={14} strokeWidth={2.2} />}
                Importer un fichier Excel
              </button>
              <input
                ref={importInputRef}
                type="file"
                accept=".xlsx"
                onChange={handleImportFile}
                style={{ display: "none" }}
              />
            </div>
            <span className="schedule-note" style={{ margin: 0, fontSize: 11.5, textAlign: "right" }}>
              Import Excel : toutes les lignes prennent l'unité « Jour » — modifiable ligne par ligne ensuite.
            </span>
          </div>
        </div>
        {importConfirmOpen && (
          <div className="card schedule-card" style={{ margin: "0 0 16px", borderColor: "var(--danger)" }}>
            <p style={{ margin: "0 0 12px", fontSize: 14 }}>
              Cet import va <strong>remplacer toutes les lignes de protocole actuelles</strong> de ce bâtiment
              par le contenu du fichier. Cette action est irréversible.
            </p>
            <div style={{ display: "flex", gap: 10 }}>
              <button
                className="delete-button"
                style={{ width: "auto", padding: "0 16px" }}
                onClick={() => {
                  setImportConfirmOpen(false);
                  importInputRef.current?.click();
                }}
              >
                Choisir le fichier et remplacer
              </button>
              <button className="add-button" onClick={() => setImportConfirmOpen(false)}>Annuler</button>
            </div>
          </div>
        )}
        {importError && (
          <p className="field-error" style={{ margin: "0 0 14px" }}>{importError}</p>
        )}
        {importResult && (
          <div
            role="status"
            style={{
              margin: "0 0 16px", padding: "11px 13px", borderRadius: 10, fontSize: 13, lineHeight: 1.5,
              background: (importResult.skipped.length || importResult.warnings?.length) ? "#fff4f0" : "var(--mint-soft, #d7f5ec)",
              color: (importResult.skipped.length || importResult.warnings?.length) ? "#8a3b1f" : "#0b5137",
            }}
          >
            <strong>
              {importResult.replaced && "Protocole remplacé — "}
              {importResult.imported} ligne{importResult.imported > 1 ? "s" : ""} importée
              {importResult.imported > 1 ? "s" : ""} avec succès
              {importResult.skipped.length > 0 && `, ${importResult.skipped.length} ligne${importResult.skipped.length > 1 ? "s" : ""} ignorée${importResult.skipped.length > 1 ? "s" : ""}`}
              .
            </strong>
            {importResult.replaced && (
              <span style={{ display: "block", marginTop: 4, fontWeight: 400 }}>
                Les lignes précédentes ont été retirées. Enregistrez pour appliquer.
              </span>
            )}
            {(importResult.skipped.length > 0 || importResult.warnings?.length > 0) && (
              <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                {importResult.skipped.map((s) => (
                  <li key={`s-${s.line}-${s.reason}`}>Ligne {s.line} : {s.reason}</li>
                ))}
                {(importResult.warnings || []).map((w, i) => (
                  <li key={`w-${w.line}-${i}`}>Ligne {w.line} : {w.reason}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        {!batchEditable && (
          <div
            role="status"
            style={{
              display: "flex", gap: 9, alignItems: "flex-start", margin: "0 0 18px",
              padding: "11px 13px", borderRadius: 10,
              background: "var(--mint-soft, #d7f5ec)", color: "#0b5137", fontSize: 13, lineHeight: 1.45,
            }}
          >
            <Info size={15} strokeWidth={2} style={{ flexShrink: 0, marginTop: 1 }} />
            <span>
              Ce bâtiment n'a pas de bande active. Le protocole ci-dessous s'appliquera à la
              prochaine bande démarrée ici — son nom, son effectif et la fréquence de pesée se
              définissent au démarrage d'une bande, via « Nouvelle bande ».
            </span>
          </div>
        )}
        <div className="detail-grid">
          {/* Hidden outright when the house has no active batch, rather than shown disabled
              (2026-09-11): there is no batch to name, so an inert field just invites the
              question "why can't I type here?". The notice above already explains that a
              batch's name is set when one is started. The other batch-scoped fields stay
              visible-but-disabled — they describe the protocol that will apply to the next
              batch, so seeing their values is still useful. */}
          {batchEditable && (
            <label className="field">
              <span>Nom de la bande</span>
              <input
                value={batchName}
                onChange={(e) => setBatchName(e.target.value)}
                onBlur={() => setBatchNameTouched(true)}
                placeholder="ex. Bande printemps 2026"
                required={mode === "onboarding"}
                aria-invalid={batchNameMissing && (batchNameTouched || totalRows > 0)}
              />
              {batchNameMissing && (batchNameTouched || totalRows > 0) && (
                <span className="field-error" style={{ margin: "4px 0 0", fontSize: 12 }}>
                  Le nom de la bande est requis.
                </span>
              )}
            </label>
          )}
          <label className="field">
            <span>Nom du bâtiment</span>
            <input value={buildingName} onChange={(e) => setBuildingName(e.target.value)} placeholder="ex. Bâtiment A" />
          </label>
          <label className="field">
            <span>Poussins mis en place</span>
            <input type="number" value={chicksPlaced} onChange={(e) => setChicksPlaced(e.target.value)} placeholder="500" disabled={!batchEditable} />
          </label>
          <label className="field">
            <span>Cycle de croissance</span>
            <div className="inline-field">
              <input type="number" value={growthCycle} onChange={(e) => setGrowthCycle(e.target.value)} disabled={!batchEditable} />
              <select value={growthCycleUnit} onChange={(e) => setGrowthCycleUnit(e.target.value)} disabled={!batchEditable}>
                {UNITS.map((u) => (
                  <option key={u} value={u}>{UNIT_LABELS_PLURAL[u]}</option>
                ))}
              </select>
            </div>
          </label>
          <label className="field">
            <span>Fréquence de pesée (optionnel)</span>
            <select value={weighingFrequency} onChange={(e) => setWeighingFrequency(e.target.value)} disabled={!batchEditable}>
              <option value="">Aucun rappel</option>
              {UNITS.map((u) => (
                <option key={u} value={u.toUpperCase()}>{UNIT_LABELS_PLURAL[u]}</option>
              ))}
            </select>
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
        <ConfirmDialog
          message={`Supprimer la catégorie « ${confirmDeleteCategory.label} » supprimera aussi toutes ses lignes de protocole (${(schedules[confirmDeleteCategory.id] || []).length} ligne(s)). Cette action est définitive. Continuer ?`}
          confirmLabel="Supprimer la catégorie"
          onConfirm={() => deleteCategory(confirmDeleteCategory)}
          onCancel={() => { setConfirmDeleteCategory(null); setCategoryDeleteError(""); }}
          busy={categoryBusy}
          error={categoryDeleteError}
        />
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

              <div
                className="schedule-row-timeslots"
                style={{ gridColumn: "1 / -1", display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 4 }}
              >
                <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--muted)", letterSpacing: ".1em", textTransform: "uppercase" }}>
                  Horaires
                </span>
                {(row.timeSlots || []).map((slot) => (
                  <span
                    key={slot.id}
                    className="time-slot-chip"
                    style={{
                      display: "inline-flex", alignItems: "center", gap: 6, padding: "4px 9px", borderRadius: 999,
                      background: "var(--mint-soft)", color: "#0b6e52", fontSize: 12, fontWeight: 600,
                    }}
                  >
                    {formatSlotTime(slot.startTime)}–{formatSlotTime(slot.endTime)}
                    <button
                      type="button"
                      onClick={() => removeTimeSlot(row.id, slot.id)}
                      aria-label={`Supprimer le créneau ${formatSlotTime(slot.startTime)}–${formatSlotTime(slot.endTime)}`}
                      style={{ border: 0, background: "none", padding: 0, cursor: "pointer", color: "inherit", display: "flex" }}
                    >
                      <X size={11} strokeWidth={2.5} />
                    </button>
                  </span>
                ))}

                {addingSlotForRow === row.id ? (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                    <input type="time" value={slotStart} onChange={(e) => setSlotStart(e.target.value)} style={{ width: 100 }} />
                    <span style={{ color: "var(--muted)" }}>–</span>
                    <input type="time" value={slotEnd} onChange={(e) => setSlotEnd(e.target.value)} style={{ width: 100 }} />
                    <button type="button" className="icon-button" onClick={() => confirmAddSlot(row.id)} aria-label="Confirmer le créneau">
                      <Check size={13} strokeWidth={2.2} />
                    </button>
                    <button type="button" className="icon-button" onClick={() => setAddingSlotForRow(null)} aria-label="Annuler le créneau">
                      <X size={13} strokeWidth={2.2} />
                    </button>
                    {slotError && <span className="field-error" style={{ fontSize: 11, margin: 0 }}>{slotError}</span>}
                  </span>
                ) : (
                  <button
                    type="button"
                    className="add-button"
                    style={{ marginTop: 0, padding: "4px 10px", fontSize: 11 }}
                    onClick={() => openAddSlot(row.id)}
                  >
                    <Plus size={12} strokeWidth={2.2} />
                    Ajouter un créneau
                  </button>
                )}
              </div>

              {(stockItemList.length > 0 || farmId) && (
                <div
                  className="schedule-row-consumption"
                  style={{ gridColumn: "1 / -1", display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 4 }}
                >
                  <span style={{ fontSize: 10.5, fontWeight: 700, color: "var(--muted)", letterSpacing: ".1em", textTransform: "uppercase" }}>
                    Consommation
                  </span>
                  <ResourceCombobox
                    items={stockItemList}
                    value={row.stockItemCode}
                    onSelect={(code) => {
                      updateRow(row.id, "stockItemCode", code);
                      checkCoverage(row.id, { stockItemCode: code });
                    }}
                    onCreate={farmId ? createStockItem : undefined}
                  />
                  {row.stockItemCode && createdInlineCodes.has(row.stockItemCode) && (
                    <UnitField
                      value={stockItemList.find((s) => s.item_code === row.stockItemCode)?.unit || ""}
                      onChange={(u) => setStockItemUnit(row.stockItemCode, u)}
                    />
                  )}
                  <select
                    aria-label="Mode de dosage"
                    value={row.consumptionMode}
                    onChange={(e) => {
                      updateRow(row.id, "consumptionMode", e.target.value);
                      checkCoverage(row.id, { consumptionMode: e.target.value });
                    }}
                    style={{ minWidth: 150 }}
                    disabled={!row.stockItemCode}
                  >
                    <option value="fixed">Quantité fixe / jour</option>
                    <option value="dose">Dose par bande</option>
                  </select>
                  {row.consumptionMode === "dose" ? (
                    <input
                      type="number"
                      min="0"
                      step="any"
                      placeholder="Dose / oiseau"
                      aria-label="Dose par oiseau"
                      value={row.dosePerBird}
                      onChange={(e) => updateRow(row.id, "dosePerBird", e.target.value)}
                      onBlur={(e) => checkCoverage(row.id, { dosePerBird: e.target.value })}
                      style={{ width: 130 }}
                      disabled={!row.stockItemCode}
                    />
                  ) : (
                    <input
                      type="number"
                      min="0"
                      step="any"
                      placeholder="Quantité/jour"
                      aria-label="Quantité par jour"
                      value={row.quantityPerDay}
                      onChange={(e) => updateRow(row.id, "quantityPerDay", e.target.value)}
                      onBlur={(e) => checkCoverage(row.id, { quantityPerDay: e.target.value })}
                      style={{ width: 130 }}
                      disabled={!row.stockItemCode}
                    />
                  )}
                  {row.coverageWarning && (
                    <span className="field-error" style={{ flexBasis: "100%", margin: 0, fontSize: 12 }}>
                      {row.coverageWarning}
                    </span>
                  )}
                </div>
              )}
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
        <span
          className={`save-message ${saveError ? "error" : saveMessage ? "success" : ""}`}
          role={saveError ? "alert" : undefined}
        >
          {saveError || saveMessage}
        </span>
        {onAddAnother && (
          <button className="add-button" style={{ marginTop: 0 }} onClick={handleAddAnother} disabled={saving || totalRows === 0 || batchNameMissing}>
            {saving ? <Loader2 size={16} className="spin" /> : "Ajouter ce bâtiment et en configurer un autre"}
          </button>
        )}
        <button className="save-button" onClick={handleSave} disabled={saving || totalRows === 0 || batchNameMissing}>
          {saving ? <Loader2 size={16} className="spin" /> : submitLabel || (mode === "onboarding" ? "Suivant" : "Enregistrer le protocole")}
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
