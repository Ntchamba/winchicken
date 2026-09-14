import { useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { maintenanceApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";

/**
 * "Signaler un cas inhabituel" mini-form — extracted from `HouseDetailPage` (2026-08-25) as
 * its own component. `POST /api/unusual-cases/` already existed (open to any authenticated
 * user of the farm) before this had any frontend consumer.
 *
 * @param {string} batchCode
 * @param {() => void} [onReported]
 * @param {boolean} [startOpen] - Skip the collapsed "Signaler un cas inhabituel" button and
 *   render the textarea directly (2026-08-26, for the sidebar-wide shortcut in
 *   IncidentShortcut.jsx — that flow already required picking a house/batch first, so an extra
 *   click to reveal the form on top of that would violate "one or two clicks" for what's meant
 *   to be a low-friction urgent-reporting path). Defaults to `false`, so HouseDetailPage's
 *   existing per-house usage is unaffected.
 */
export default function UnusualCaseReportForm({ batchCode, onReported, startOpen = false }) {
  const { user } = useAuth();
  const [open, setOpen] = useState(startOpen);
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!description.trim()) return;
    setSaving(true);
    try {
      await maintenanceApi.addCase({
        batch: batchCode,
        farmer: user.role === "FARMER" ? user.id : null,
        worker: user.role === "WORKER" ? user.id : null,
        case_description: description.trim(),
      });
      setDescription("");
      setOpen(false);
      onReported?.();
    } finally {
      setSaving(false);
    }
  };

  if (!open) {
    // Was a plain `.section-link` (small text, mint) — too easy to miss for something that
    // should read as a flag, not a routine nav action (2026-08-26). `--warning`, not `--danger`:
    // this isn't destructive like the delete-button actions elsewhere on this page, it's an
    // alert-worthy observation, so amber reads correctly next to those without looking like a
    // third destructive action.
    return (
      <button className="report-issue-button" onClick={() => setOpen(true)}>
        <AlertTriangle size={18} strokeWidth={2} />
        Signaler un cas inhabituel
      </button>
    );
  }

  return (
    <form className="card schedule-card" onSubmit={handleSubmit} style={{ marginTop: 10 }}>
      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Décrire l'observation (symptômes, comportement…)"
        rows={3}
        style={{ width: "100%", border: "1px solid var(--line)", borderRadius: 9, padding: 10, fontSize: 13.5, fontFamily: "inherit" }}
      />
      <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
        <button type="submit" className="save-button" disabled={saving || !description.trim()} style={{ width: "auto", padding: "0 16px" }}>
          {saving ? <Loader2 size={16} className="spin" /> : "Signaler"}
        </button>
        <button type="button" className="add-button" onClick={() => { setOpen(false); setDescription(""); }}>Annuler</button>
      </div>
    </form>
  );
}
