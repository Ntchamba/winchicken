import { useEffect, useRef } from "react";
import { Printer, X } from "lucide-react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { useAuth } from "../context/AuthContext";
import "../styles/protocol-edit-modal.css";
import "../styles/receipt.css";

const PRODUCT_LABELS = { BIRD: "Volaille", EGG: "Œufs", CULL: "Réforme", MANURE: "Fumier" };

/**
 * Printable sale receipt (2026-08-26, docs/deviations.md Part 15, Part D) — no PDF library
 * exists anywhere in this codebase (`BatchClosingReport` is JSON data, never rendered as a
 * file), so this uses the browser's own print dialog (`window.print()`) rather than adding one:
 * WeasyPrint/reportlab would need system-level deps (Pango/Cairo for WeasyPrint) baked into
 * `backend/Dockerfile` for a single, low-traffic feature, and the task explicitly allows "a
 * clean print-styled view" as the alternative. "Downloadable" is covered by the browser's own
 * print dialog "Save as PDF" destination — no separate export path needed.
 *
 * `.receipt-print-area` (styles/receipt.css) is the only thing visible in the print output —
 * everything else on the page (sidebar, modal backdrop, the rest of the app) is hidden via
 * `@media print`, so printing from here never leaks the surrounding dashboard chrome onto paper.
 *
 * @param {?object} sale - Sale row (from GET /api/sales/ — { id, product_type, quantity, unit_price, total_amount, sale_date, customer }); modal closed when null.
 * @param {() => void} onClose
 */
export default function ReceiptModal({ sale, onClose }) {
  const { user } = useAuth();
  const open = !!sale;
  const reduceMotion = useReducedMotion();
  const panelRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKeyDown);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  const transition = { duration: reduceMotion ? 0 : 0.25, ease: [0.16, 1, 0.3, 1] };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="protocol-modal-backdrop"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={transition}
          onClick={onClose}
        >
          <motion.div
            ref={panelRef}
            className="protocol-modal-panel"
            style={{ width: "min(420px,100%)" }}
            role="dialog" aria-modal="true" aria-label="Reçu de vente" tabIndex={-1}
            initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.96 }}
            transition={transition}
            onClick={(e) => e.stopPropagation()}
          >
            <button className="protocol-modal-close" onClick={onClose} aria-label="Fermer">
              <X size={18} strokeWidth={2} />
            </button>

            <div className="receipt-print-area" style={{ padding: "44px 32px 28px" }}>
              <p className="eyebrow" style={{ textAlign: "center" }}>WINCHICKEN</p>
              <h2 style={{ textAlign: "center", margin: "4px 0 2px", fontFamily: "'Space Grotesk',sans-serif" }}>Reçu de vente</h2>
              <p style={{ textAlign: "center", margin: "0 0 20px", color: "var(--muted)", fontSize: 13 }}>{user.farm_name}</p>

              <div className="receipt-row"><span>Reçu N°</span><strong>{sale.id}</strong></div>
              <div className="receipt-row"><span>Date</span><strong>{sale.sale_date}</strong></div>
              <div className="receipt-row"><span>Produit</span><strong>{PRODUCT_LABELS[sale.product_type] || sale.product_type}</strong></div>
              <div className="receipt-row"><span>Quantité</span><strong>{sale.quantity}</strong></div>
              <div className="receipt-row"><span>Prix unitaire</span><strong>{sale.unit_price}</strong></div>
              {sale.customer && <div className="receipt-row"><span>Client</span><strong>{sale.customer}</strong></div>}
              <div className="receipt-row receipt-total"><span>Total</span><strong>{sale.total_amount}</strong></div>
            </div>

            <div style={{ padding: "0 32px 28px", display: "flex", justifyContent: "flex-end" }} className="receipt-no-print">
              <button className="save-button" style={{ width: "auto" }} onClick={() => window.print()}>
                <Printer size={16} strokeWidth={1.8} style={{ marginRight: 6 }} />
                Imprimer / Enregistrer en PDF
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
