import { Loader2 } from "lucide-react";

/**
 * Inline destructive-action confirmation card (2026-08-25) — extracted from the pattern
 * already duplicated in `HouseDetailPage` (batch closing) and `HouseProtocolForm` (category
 * deletion): a `.card.schedule-card` with a danger border, a message, and confirm/cancel
 * buttons. New destructive actions (batch deletion) reuse this instead of a third copy.
 *
 * @param {string} message - Warning text, including any consequence (e.g. what cascades).
 * @param {string} [confirmLabel] - Text on the confirm button (default "Confirmer").
 * @param {() => void} onConfirm
 * @param {() => void} onCancel
 * @param {boolean} [busy] - Shows a spinner and disables the confirm button.
 */
export default function ConfirmDialog({ message, confirmLabel = "Confirmer", onConfirm, onCancel, busy = false }) {
  return (
    <div className="card schedule-card" style={{ marginBottom: 18, borderColor: "var(--danger)" }}>
      <p style={{ margin: "0 0 12px", fontSize: 14 }}>{message}</p>
      <div style={{ display: "flex", gap: 10 }}>
        <button className="delete-button" style={{ width: "auto", padding: "0 16px" }} onClick={onConfirm} disabled={busy}>
          {busy ? <Loader2 size={16} className="spin" /> : confirmLabel}
        </button>
        <button className="add-button" onClick={onCancel} disabled={busy}>Annuler</button>
      </div>
    </div>
  );
}
