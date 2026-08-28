import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import StockParametersForm from "./StockParametersForm";
import { stockApi } from "../api/endpoints";
import "../styles/protocol-edit-modal.css";

const EASE_EXPO = [0.16, 1, 0.3, 1];
const FOCUSABLE = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

let localRowId = 5000;

// Flat StockItemSerializer list -> `{ [categoryId]: [row] }` in the shape StockParametersForm
// wants. Rows for a category with no items still get an entry so the tab renders empty.
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
export default function StockParametersModal({ open, farmId, onClose, onSaved }) {
  const reduceMotion = useReducedMotion();
  const panelRef = useRef(null);
  const dirtyRef = useRef(false);
  const triggerRef = useRef(null);

  const [categories, setCategories] = useState(null);
  const [data, setData] = useState(null);
  const [suppliers, setSuppliers] = useState([]);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  const loadSuppliers = () => {
    stockApi.suppliers(farmId).then(({ data: d }) => setSuppliers(d.results || d));
  };

  useEffect(() => {
    if (!open) return;
    setCategories(null);
    setData(null);
    dirtyRef.current = false;
    triggerRef.current = document.activeElement;

    Promise.all([stockApi.categories(farmId), stockApi.items(farmId), stockApi.suppliers(farmId)])
      .then(([catRes, itemRes, supRes]) => {
        const cats = catRes.data.results || catRes.data;
        setCategories(cats);
        setData(buildData(itemRes.data.items, cats));
        setSuppliers(supRes.data.results || supRes.data);
      });
  }, [open, farmId]);

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
      await stockApi.putItems(farmId, payload.items);
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
