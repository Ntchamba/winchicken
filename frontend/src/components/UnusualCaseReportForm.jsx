import { useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { maintenanceApi } from "../api/endpoints";
import { getServerErrorMessage } from "../api/errors";
import { useAuth } from "../context/AuthContext";

/**
 * "Signaler un cas inhabituel" mini-form — extracted from `HouseDetailPage` (2026-08-25) as
 * its own component. `POST /api/unusual-cases/` already existed (open to any authenticated
 * user of the farm) before this had any frontend consumer.
 *
 * Feedback (2026-09-16, FIX 8 group 2): the submit was `try {} finally {}` with no catch, so a
 * rejected report closed nothing, said nothing and left the worker looking at a form that had
 * simply stopped spinning. On the `HouseDetailPage` call site there was no confirmation either
 * — the form collapsed and "Cas signalés" above it did not move, which reads as "it did not go
 * through" and gets the same case reported twice. Now: caught errors keep the text so it can be
 * re-sent, and a success says so in place of the button.
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
  const [error, setError] = useState("");
  const [reported, setReported] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (saving || !description.trim()) return;
    setSaving(true);
    setError("");
    try {
      await maintenanceApi.addCase({
        batch: batchCode,
        farmer: user.role === "FARMER" ? user.id : null,
        worker: user.role === "WORKER" ? user.id : null,
        case_description: description.trim(),
      });
      setDescription("");
      setOpen(false);
      setReported(true);
      onReported?.();
    } catch (err) {
      // The text stays in the textarea: whoever just described a sick bird must not have to
      // type it again to find out whether it was sent.
      setError(getServerErrorMessage(err, "Le signalement n'a pas été envoyé. Réessayez."));
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
      <>
        {reported && (
          <p className="save-message success" style={{ margin: "0 0 8px" }}>
            Cas signalé. Il apparaît dans « Cas signalés ».
          </p>
        )}
        <button className="report-issue-button" onClick={() => { setReported(false); setOpen(true); }}>
          <AlertTriangle size={18} strokeWidth={2} />
          Signaler un cas inhabituel
        </button>
      </>
    );
  }

  return (
    <form className="card schedule-card" onSubmit={handleSubmit} style={{ marginTop: 10 }}>
      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        aria-label="Description du cas"
        placeholder="Décrire l'observation (symptômes, comportement…)"
        rows={3}
        style={{ width: "100%", border: "1px solid var(--line)", borderRadius: 9, padding: 10, fontSize: 13.5, fontFamily: "inherit" }}
      />
      <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
        <button type="submit" className="save-button" disabled={saving || !description.trim()} style={{ width: "auto", padding: "0 16px" }}>
          {saving ? <><Loader2 size={16} className="spin" /> Envoi…</> : "Signaler"}
        </button>
        <button type="button" className="add-button" onClick={() => { setOpen(false); setDescription(""); setError(""); }}>Annuler</button>
      </div>
      {error && <p className="field-error" style={{ margin: "10px 0 0" }} role="alert">{error}</p>}
    </form>
  );
}
