import { useEffect, useRef, useState } from "react";
import { X, FileSpreadsheet, Download, Loader2 } from "lucide-react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import StockParametersForm from "./StockParametersForm";
import { stockApi } from "../api/endpoints";
import { getServerErrorMessage } from "../api/errors";
import "../styles/protocol-edit-modal.css";

const EASE_EXPO = [0.16, 1, 0.3, 1];
const FOCUSABLE = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

let localRowId = 5000;
const todayISO = () => new Date().toISOString().slice(0, 10);

// Flat StockItemSerializer list -> `{ [categoryId]: [row] }` in the shape StockParametersForm
// wants. Rows for a category with no items still get an entry so the tab renders empty.
// `quantity` is pre-filled with the item's current on-hand so the Quantité column round-trips
// safely: the PUT below fully replaces StockItem rows (cascading away their StockMovement
// history), and handleSave then re-records each row's quantity as a single IN movement.
function buildData(items, categories) {
  const map = Object.fromEntries(categories.map((c) => [c.id, []]));
  for (const item of items) {
    (map[item.category] ||= []).push({
      id: localRowId++,
      itemCode: item.item_code,
      item: item.name,
      feedStage: item.feed_stage || "STARTER",
      coldChain: !!item.cold_chain_required,
      threshold: item.alert_threshold,
      unit: item.unit,
      price: item.unit_price,
      supplier: item.supplier ?? null,
      itemType: item.item_type || "",
      quantity: item.current_quantity ?? "",
      originalQuantity: item.current_quantity ?? 0,
      date: todayISO(),
    });
  }
  return map;
}

/**
 * "Mettre à jour le stock" — the stock parameter form as a centered backdrop-blur modal, same
 * visual language / focus-trap / dirty-tracking as `ProtocolEditModal` (reuses its
 * `.protocol-modal-*` chrome). On save it persists via PUT /api/farms/{farmId}/stock-items/,
 * closes, and calls `onSaved` so the underlying charts/suppliers refresh immediately.
 *
 * @param {boolean} open
 * @param {number} farmId
 * @param {() => void} onClose - X button, backdrop, Escape (confirms if the form has edits).
 * @param {() => void} onSaved - called right after a successful save, then the modal closes.
 */
export default function StockParametersModal({ open, farmId, compositions = [], onClose, onSaved }) {
  const reduceMotion = useReducedMotion();
  const panelRef = useRef(null);
  const dirtyRef = useRef(false);
  const triggerRef = useRef(null);

  const [categories, setCategories] = useState(null);
  const [data, setData] = useState(null);
  const [suppliers, setSuppliers] = useState([]);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  const importInputRef = useRef(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null); // { updated, created, skipped:[{line,reason}] }
  const [importError, setImportError] = useState("");

  const loadSuppliers = () => {
    stockApi.suppliers(farmId).then(({ data: d }) => setSuppliers(d.results || d));
  };

  const reload = () =>
    Promise.all([stockApi.categories(farmId), stockApi.items(farmId), stockApi.suppliers(farmId)])
      .then(([catRes, itemRes, supRes]) => {
        const cats = catRes.data.results || catRes.data;
        setCategories(cats);
        setData(buildData(itemRes.data.items, cats));
        setSuppliers(supRes.data.results || supRes.data);
      });

  useEffect(() => {
    if (!open) return;
    setCategories(null);
    setData(null);
    setImportResult(null);
    setImportError("");
    dirtyRef.current = false;
    triggerRef.current = document.activeElement;
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, farmId]);

  const handleImportFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setImporting(true);
    setImportError("");
    setImportResult(null);
    try {
      const { data: res } = await stockApi.importXlsx(farmId, file);
      await reload();
      onSaved?.();
      setImportResult(res);
    } catch (err) {
      setImportError(getServerErrorMessage(err, "Échec de l'import du fichier Excel."));
    } finally {
      setImporting(false);
    }
  };

  const requestClose = () => {
    if (dirtyRef.current && !window.confirm("Fermer sans enregistrer les modifications ?")) return;
    onClose();
    triggerRef.current?.focus?.();
  };

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e) => {
      if (e.key === "Escape") { requestClose(); return; }
      if (e.key !== "Tab" || !panelRef.current) return;
      const focusable = panelRef.current.querySelectorAll(FOCUSABLE);
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
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
  }, [open]);

  const handleSave = async (payload) => {
    setSaving(true);
    setSaveError("");
    try {
      // 1. Persist the item definitions (full replace).
      const { data } = await stockApi.putItems(farmId, payload.items);
      // 2. Record the Quantité / Date columns as stock IN movements. The PUT above recreated
      //    every StockItem (and cascaded away prior movements), so re-post each row's quantity
      //    against the fresh item_code, matched back by name.
      const byName = {};
      for (const it of data.items || []) byName[it.name] = it;
      const movements = (payload.items || [])
        .filter((it) => it.quantity != null && Number(it.quantity) > 0 && byName[it.name])
        .map((it) => {
          // Adding a brand-new article to stock is a purchase: file it in Finances at
          // quantity × unit price (the backend turns total_price into the Expense, under the
          // category the article's type implies). Re-saving an existing item's stock level
          // sends nothing → no double-count.
          const unitPrice = Number(byName[it.name].unit_price) || 0;
          const totalPrice = it.is_new_item && unitPrice > 0 ? Number(it.quantity) * unitPrice : null;
          // Composed item whose level was raised here → treat the increase as a production run:
          // deduct the recipe ingredients scaled to the delta (backend, via production_quantity).
          const delta = Number(it.quantity) - (Number(it.original_quantity) || 0);
          const production = it.deduct_production && delta > 0 ? delta : null;
          return stockApi.addMovement({
            item: byName[it.name].item_code,
            movement_type: "IN",
            quantity: Number(it.quantity),
            movement_date: it.movement_date || todayISO(),
            note: "Saisie via « Mettre à jour le stock »",
            ...(totalPrice && totalPrice > 0 ? { total_price: totalPrice } : {}),
            ...(production ? { production_quantity: production } : {}),
          });
        });
      if (movements.length) await Promise.all(movements);

      dirtyRef.current = false;
      onSaved?.();
      onClose();
      triggerRef.current?.focus?.();
    } catch (err) {
      setSaveError(err.response?.data?.detail || "Impossible d'enregistrer les paramètres. Réessayez.");
      throw err;
    } finally {
      setSaving(false);
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
            className="protocol-modal-panel"
            role="dialog"
            aria-modal="true"
            aria-label="Mettre à jour le stock"
            tabIndex={-1}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={panelTransition}
            onClick={(e) => e.stopPropagation()}
            onInputCapture={() => { dirtyRef.current = true; }}
            onChangeCapture={() => { dirtyRef.current = true; }}
          >
            <button className="protocol-modal-close" onClick={requestClose} aria-label="Fermer">
              <X size={18} strokeWidth={2} />
            </button>
            {saveError && <p className="protocol-modal-error">{saveError}</p>}

            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, margin: "4px 0 14px" }}>
              <a className="add-button" style={{ marginTop: 0, textDecoration: "none" }} href={stockApi.importTemplateUrl}>
                <Download size={14} strokeWidth={2.2} /> Télécharger un modèle
              </a>
              <button
                className="add-button"
                style={{ marginTop: 0 }}
                onClick={() => importInputRef.current?.click()}
                disabled={importing}
              >
                {importing ? <Loader2 size={14} className="spin" /> : <FileSpreadsheet size={14} strokeWidth={2.2} />}
                Importer un fichier Excel
              </button>
              <input ref={importInputRef} type="file" accept=".xlsx" onChange={handleImportFile} style={{ display: "none" }} />
              <span className="schedule-note" style={{ margin: 0, fontSize: 11.5 }}>
                Met à jour ou crée des articles par nom — ne supprime rien, ne change aucune quantité.
              </span>
            </div>
            {importError && <p className="field-error" style={{ margin: "0 0 12px" }}>{importError}</p>}
            {importResult && (
              <div
                role="status"
                style={{
                  margin: "0 0 14px", padding: "11px 13px", borderRadius: 10, fontSize: 13, lineHeight: 1.5,
                  background: importResult.skipped.length ? "#fff4f0" : "var(--mint-soft, #d7f5ec)",
                  color: importResult.skipped.length ? "#8a3b1f" : "#0b5137",
                }}
              >
                <strong>
                  {importResult.updated} ligne{importResult.updated > 1 ? "s" : ""} mise{importResult.updated > 1 ? "s" : ""} à jour,{" "}
                  {importResult.created} ligne{importResult.created > 1 ? "s" : ""} créée{importResult.created > 1 ? "s" : ""},{" "}
                  {importResult.skipped.length} ligne{importResult.skipped.length > 1 ? "s" : ""} ignorée{importResult.skipped.length > 1 ? "s" : ""}.
                </strong>
                {importResult.skipped.length > 0 && (
                  <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                    {importResult.skipped.map((s) => <li key={s.line}>Ligne {s.line} : {s.reason}</li>)}
                  </ul>
                )}
              </div>
            )}

            {categories && data ? (
              <StockParametersForm
                initialData={data}
                initialCategories={categories}
                initialSuppliers={suppliers}
                farmId={farmId}
                mode="management"
                saving={saving}
                onSave={handleSave}
                onSuppliersChanged={loadSuppliers}
                compositions={compositions}
                showStockEntry
              />
            ) : (
              <p className="empty-state" style={{ margin: 40 }}>Chargement…</p>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
