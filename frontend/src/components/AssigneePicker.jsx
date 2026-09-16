import { useEffect, useRef, useState } from "react";
import { Check, Loader2, Users } from "lucide-react";
import "./assignee-picker.css";

/**
 * "Qui fait cette tâche" — the one control that changes a task's assignees (2026-09-16, FIX 7).
 *
 * A protocol line carries a *set* of workers since FIX 7, so this replaces the single
 * `<select>` that used to live inline in `TasksNowPanel`. It is shared with
 * `AssignmentsPanel` rather than copied: those two are the only screens that can assign, and
 * "two paths computing the same thing" is how assignment display broke before (FIX 4).
 *
 * Every toggle sends the **whole** set immediately instead of collecting changes behind a save
 * button: the server `set()`s it (idempotent), and a worker on a phone who taps a name and
 * walks away must not silently lose the change to an unpressed button.
 *
 * @param {{id: number, name: string}[]} users - Everyone assignable (`GET /api/tasks/assignable-users/`).
 * @param {number[]} assignedTo - Currently assigned ids.
 * @param {string[]} assignedToNames - Their names, parallel to `assignedTo`.
 * @param {?number} currentUserId - Marks "(vous)" in the summary.
 * @param {boolean} [disabled]
 * @param {(ids: number[]) => Promise<unknown>} onChange - Must resolve once the server accepted
 *   the new set; a rejection is shown to the user rather than swallowed.
 */
export default function AssigneePicker({
  users, assignedTo = [], assignedToNames = [], currentUserId = null, disabled = false, onChange,
}) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const savedTimer = useRef(null);

  useEffect(() => () => clearTimeout(savedTimer.current), []);

  const toggle = async (userId, checked) => {
    const next = checked
      ? [...assignedTo, userId]
      : assignedTo.filter((id) => id !== userId);
    setSaving(true);
    setError("");
    setSaved(false);
    try {
      await onChange(next);
      setSaved(true);
      clearTimeout(savedTimer.current);
      savedTimer.current = setTimeout(() => setSaved(false), 3000);
    } catch {
      setError("L'affectation n'a pas été enregistrée. Réessayez.");
    } finally {
      setSaving(false);
    }
  };

  const summary = assignedToNames.length === 0
    ? "Non assignée"
    : `Assignée à ${assignedToNames.join(", ")}`;
  const mine = currentUserId != null && assignedTo.includes(currentUserId);

  return (
    <div className="assignee-picker">
      <div className="assignee-picker-row">
        <span className="task-assignee-label">{summary}{mine ? " (vous)" : ""}</span>
        <button
          type="button"
          className="assignee-picker-toggle"
          aria-expanded={open}
          disabled={disabled}
          onClick={() => setOpen((value) => !value)}
        >
          <Users size={14} strokeWidth={1.9} />
          {open ? "Fermer" : "Modifier"}
        </button>
      </div>

      {open && (
        <div className="assignee-picker-list" role="group" aria-label="Personnes assignées">
          {users.length === 0 ? (
            <p className="empty-state" style={{ margin: 0 }}>Aucun compte à assigner.</p>
          ) : (
            users.map((candidate) => (
              <label key={candidate.id} className="assignee-picker-option">
                <input
                  type="checkbox"
                  checked={assignedTo.includes(candidate.id)}
                  disabled={disabled || saving}
                  onChange={(e) => toggle(candidate.id, e.target.checked)}
                />
                <span>{candidate.name}</span>
              </label>
            ))
          )}
        </div>
      )}

      {saving && (
        <span className="assignee-picker-status">
          <Loader2 size={13} className="spin" /> Enregistrement…
        </span>
      )}
      {!saving && saved && (
        <span className="assignee-picker-status assignee-picker-status--ok">
          <Check size={13} strokeWidth={2.6} /> Affectation enregistrée.
        </span>
      )}
      {error && <p className="field-error assignee-picker-error">{error}</p>}
    </div>
  );
}
