import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import HouseProtocolForm from "./HouseProtocolForm";
import { batchesApi, housesApi, stockApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { useHousesContext } from "../context/HousesContext";
import { buildProtocolSchedules } from "../utils/protocolRows";
import "../styles/protocol-edit-modal.css";
import { fetchAllPages } from "../api/pagination";
import { toStockItemOption } from "../hooks/useStockItemOptions";

const EASE_EXPO = [0.16, 1, 0.3, 1];
const FOCUSABLE = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

// batch.planned_end_date - batch.start_date, in whole days, for the "Cycle de croissance"
// field's read-back — the form only ever stores a single value+unit pair, so an existing batch
// is shown back in days regardless of which unit it might have been entered in originally.
function daysBetween(startDate, endDate) {
  if (!startDate || !endDate) return null;
  const days = Math.round((new Date(endDate) - new Date(startDate)) / 86400000);
  return Number.isFinite(days) && days > 0 ? days : null;
}


/**
 * Protocol editor as a centered modal (2026-08-25) — replaces full-page navigation to
 * `/dashboard/houses/{houseCode}/protocol` from the "Modifier" entry points (global-view batch
 * legend, per-house header). Same visual language as `DemoVideoModal`: backdrop fades in and
 * blurs the content behind it (`backdrop-filter`, animated), the panel scales from 0.95→1 while
 * fading in. The underlying route itself keeps working unchanged for direct/shareable links —
 * a deliberate choice (see root README.md "Autonomous decisions") rather than teaching
 * `DashboardShell` to open this modal from a URL, which would need to reconcile two
 * "source of truth" mechanisms (route vs. modal open state) for no real benefit here.
 *
 * Does not touch `HouseProtocolForm`'s own fields/behavior — only fetches its data and renders
 * it inside this wrapper. "Dirty" tracking (for the close-confirmation) is a capture-phase
 * `input`/`change` listener on the panel, not a prop threaded through the form, for the same
 * reason: zero changes to the form's internals.
 *
 * Also fetches the house's active batch and passes it as `initialHeader` (2026-08-25 bugfix —
 * this used to open with an empty header, including an empty "Nom de la bande" field, even
 * though the categories/protocol-line data below it *was* correctly pre-filled; a batch rename
 * typed into that empty field also silently went nowhere on save, since `PATCH
 * /api/batches/{batchCode}/` didn't exist yet either — see `PoultryBatchDetailView`). Saving
 * now persists the name via that endpoint, strictly isolated from `PoultryHouse` — it only ever
 * touches the `PoultryBatch` row, never the house (see that view's docstring).
 *
 * @param {?string} houseCode - Which house's protocol to edit; the modal is closed when null.
 * @param {() => void} onClose - Called on close (X button, backdrop click, Escape) — always
 *   asks for confirmation first if the form has unsaved edits.
 * @param {() => void} onSaved - Called right after a successful save, then the modal closes
 *   itself (no confirmation needed at that point — the edits are saved, not discarded). The
 *   caller should refetch whatever depends on the protocol here (growth curves, the
 *   "tâches à effectuer maintenant" panel) — this is the live-propagation connection point.
 */
export default function ProtocolEditModal({ houseCode, onClose, onSaved }) {
  const open = !!houseCode;
  const reduceMotion = useReducedMotion();
  const panelRef = useRef(null);
  const dirtyRef = useRef(false);
  const triggerRef = useRef(null);
  const { refetch: refetchHouses } = useHousesContext();
  const { user } = useAuth();

  const [categories, setCategories] = useState(null);
  const [schedules, setSchedules] = useState(null);
  const [initialHeader, setInitialHeader] = useState(null);
  const [activeBatch, setActiveBatch] = useState(null);
  const [stockItems, setStockItems] = useState([]);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  useEffect(() => {
    if (!houseCode) return;
    setCategories(null);
    setSchedules(null);
    setInitialHeader(null);
    setActiveBatch(null);
    setStockItems([]);
    dirtyRef.current = false;
    triggerRef.current = document.activeElement;

    Promise.all([
      // Every page: the protocol save deletes the lines it is not sent, so a category missed
      // here (paginated by 20) would lose all its lines on the next save.
      fetchAllPages((params) => housesApi.listProtocolCategories(houseCode, params)),
      housesApi.getProtocol(houseCode),
      housesApi.detail(houseCode),
      batchesApi.list(houseCode),
      stockApi.items(user.farm),
    ]).then(([categoriesRes, protocolRes, houseRes, batchesRes, stockRes]) => {
      const cats = categoriesRes;
      const batches = batchesRes.data.results || batchesRes.data;
      const batch = batches.find((b) => b.status === "ACTIVE") || null;
      setCategories(cats);
      setStockItems((stockRes.data.items || []).map(toStockItemOption));
      setSchedules(buildProtocolSchedules(cats, protocolRes.data));
      setActiveBatch(batch);
      setInitialHeader({
        buildingName: houseRes.data.name || "",
        chicksPlaced: batch?.initial_count || "",
        growthCycle: daysBetween(batch?.start_date, batch?.planned_end_date) || 56,
        growthCycleUnit: "Day",
        batchName: batch?.name || "",
        weighingFrequency: batch?.weighing_frequency || "",
      });
    });
  }, [houseCode, user.farm]);

  const requestClose = () => {
    if (dirtyRef.current && !window.confirm("Fermer sans enregistrer les modifications ?")) return;
    onClose();
    triggerRef.current?.focus?.();
  };

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e) => {
      if (e.key === "Escape") {
        requestClose();
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;
      const focusable = panelRef.current.querySelectorAll(FOCUSABLE);
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
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
      const requests = [housesApi.putProtocol(houseCode, payload.protocolLines)];

      // The "Nom du bâtiment" field was editable but its value (payload.house.buildingName)
      // was never persisted — PATCH /api/houses/{code}/ (HouseDetailView) exists but nothing
      // here called it, so renaming a house in this modal was a silent no-op (and on a house
      // with no active batch nothing at all got saved). Send a non-blank, changed name now.
      const newHouseName = (payload.house?.buildingName || "").trim();
      if (newHouseName && newHouseName !== (initialHeader?.buildingName || "")) {
        requests.push(housesApi.update(houseCode, { name: newHouseName }));
      }

      if (activeBatch) {
        const changedFields = {};
        if (payload.batchName !== activeBatch.name) changedFields.name = payload.batchName;
        if ((payload.weighingFrequency || null) !== (activeBatch.weighing_frequency || null)) {
          changedFields.weighing_frequency = payload.weighingFrequency;
        }
        if (Object.keys(changedFields).length > 0) {
          requests.push(batchesApi.quickEdit(activeBatch.batch_code, changedFields));
        }
      }
      await Promise.all(requests);
      dirtyRef.current = false;
      // Refetch the shared houses/batches list directly from here (2026-08-25) — not just via
      // the caller's onSaved — so the sidebar updates regardless of whether a given page
      // remembers to wire its own onSaved to a refresh. See HousesContext's docstring for why
      // this used to be the actual root cause of the sidebar-staleness bug.
      refetchHouses();
      onSaved?.();
      onClose();
      triggerRef.current?.focus?.();
    } catch (err) {
      // Surfaced in the panel below rather than left silent — a failed save (permission,
      // validation, network) used to leave the user with no feedback at all: the spinner just
      // stopped and the modal stayed open with nothing visibly wrong.
      setSaveError(err.response?.data?.detail || "Impossible d'enregistrer les modifications. Réessayez.");
      throw err; // re-thrown so HouseProtocolForm's own handleSave doesn't show a false "Enregistré"
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
            aria-label="Modifier le protocole du bâtiment"
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
            {categories && schedules && initialHeader ? (
              <HouseProtocolForm
                initialHeader={initialHeader}
                initialCategories={categories}
                initialSchedules={schedules}
                mode="management"
                houseCode={houseCode}
                saving={saving}
                stockItems={stockItems}
                farmId={user.farm}
                batchEditable={Boolean(activeBatch)}
                onSave={handleSave}
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
