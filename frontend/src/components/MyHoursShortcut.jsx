import { useState } from "react";
import { createPortal } from "react-dom";
import { Clock, X } from "lucide-react";
import { payrollApi } from "../api/endpoints";
import { getServerErrorMessage } from "../api/errors";
import { useDateDefaultingToToday } from "../hooks/useTodayISO";

/**
 * "Mes heures" sidebar shortcut (2026-08-27, Salaires module Part D) — self-service hours
 * logging, open to every role (not gated), same "small entry point reachable from the sidebar"
 * pattern as `IncidentShortcut.jsx` but styled as a plain `.sidebar-link` (not the warning/danger
 * treatment — logging hours isn't an alert-worthy action). Always posts to `POST /api/work-hours/`
 * with no `user` field, so the backend defaults it to the requester (self-report) — this
 * component has no way to log hours for anyone else, by design; Admin/Farm Manager do that from
 * the Salaires section itself (`SalairesSection.jsx`), not here.
 */
export default function MyHoursShortcut() {
  const [open, setOpen] = useState(false);
  const [date, setDate, today] = useDateDefaultingToToday();
  const [hours, setHours] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  const reset = () => {
    setOpen(false);
    setDate(today);
    setHours("");
    setNote("");
    setError("");
    setSaved(false);
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!hours) return;
    setSaving(true);
    setError("");
    try {
      await payrollApi.logHours({ date, hours_worked: hours, note });
      setSaved(true);
      setHours("");
      setNote("");
    } catch (err) {
      setError(getServerErrorMessage(err, "Impossible d'enregistrer ces heures."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <button className="sidebar-link" onClick={() => setOpen(true)}>
        <Clock size={16} strokeWidth={1.8} />
        Mes heures
      </button>

      {/* Portalled to <body>: the sidebar is position:sticky, a stacking context of its own, so a
          modal rendered inside it sat under the page content whatever its z-index — the task
          cards showed through "Enregistrer mes heures" (campaign 3, in the browser). */}
      {open && createPortal(
        <div
          style={{
            position: "fixed", inset: 0, zIndex: 70, display: "flex",
            alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,.4)",
          }}
        >
          <div className="card schedule-card" style={{ width: 360, maxWidth: "90vw" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
              <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: "#10242c" }}>Enregistrer mes heures</h2>
              <button onClick={reset} aria-label="Fermer" style={{ border: 0, background: "none", color: "var(--muted)", cursor: "pointer", padding: 0 }}>
                <X size={18} />
              </button>
            </div>

            <form onSubmit={submit}>
              <label className="field" style={{ marginBottom: 12 }}>
                <span>Date</span>
                <input type="date" value={date} max={today} onChange={(e) => { setDate(e.target.value); setSaved(false); }} />
              </label>
              <label className="field" style={{ marginBottom: 12 }}>
                <span>Heures travaillées</span>
                <input type="number" min="0" step="0.25" value={hours} onChange={(e) => { setHours(e.target.value); setSaved(false); }} required />
              </label>
              <label className="field" style={{ marginBottom: 14 }}>
                <span>Note (optionnel)</span>
                <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="ex. Astreinte week-end" />
              </label>
              {error && <p className="field-error" style={{ marginBottom: 10 }}>{error}</p>}
              {saved && <p style={{ color: "var(--mint)", fontSize: 13, marginBottom: 10 }}>Heures enregistrées.</p>}
              <button type="submit" className="save-button" style={{ width: "100%" }} disabled={saving}>
                {saving ? "Enregistrement…" : "Enregistrer"}
              </button>
            </form>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
