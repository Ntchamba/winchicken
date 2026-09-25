import { useEffect, useRef, useState } from "react";
import { X, FileSpreadsheet, Download, Loader2 } from "lucide-react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import StockParametersForm from "./StockParametersForm";
import { stockApi } from "../api/endpoints";
import { saveStockItemsWithQuantities } from "../api/stockSave";
import { buildStockRows } from "../utils/stockRows";
import { getServerErrorMessage } from "../api/errors";
import "../styles/protocol-edit-modal.css";
import { fetchAllPages } from "../api/pagination";

const EASE_EXPO = [0.16, 1, 0.3, 1];
const FOCUSABLE = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';


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
    fetchAllPages((params) => stockApi.suppliers(farmId, params)).then(setSuppliers);
  };

  const reload = () =>
    // Every page of categories and suppliers: the save sends the items of the categories the form
    // has, and the stock PUT deletes every item it is not sent (CASCADE to its movements). Both
    // lists are paginated by 20, so page 1 alone would have wiped the 21st category's items.
    Promise.all([
      fetchAllPages((params) => stockApi.categories(farmId, params)),
      stockApi.items(farmId),
      fetchAllPages((params) => stockApi.suppliers(farmId, params)),
    ])
      .then(([cats, itemRes, sups]) => {
        setCategories(cats);
        setData(buildStockRows(itemRes.data.items, cats));
        setSuppliers(sups);
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
      await saveStockItemsWithQuantities(farmId, payload.items, {
        note: "Saisie via « Mettre à jour le stock »",
      });

      dirtyRef.current = false;
      onSaved?.();
      onClose();
      triggerRef.current?.focus?.();
    } catch (err) {
      setSaveError(getServerErrorMessage(err, "Impossible d'enregistrer les paramètres. Réessayez."));
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
