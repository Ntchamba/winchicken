import { useEffect, useRef, useState } from "react";
import { getServerErrorMessage } from "../api/errors";
import { Check, Loader2, Search, Users } from "lucide-react";
import { tasksApi } from "../api/endpoints";
import "./assignee-picker.css";

// How many names one search shows. A real farm (under 50 accounts) sees everyone without
// typing; at 20 000 accounts the full list was 1 MB per screen (load test, 2026-09-25).
export const PICKER_LIMIT = 50;

const searchAssignableUsers = (query) =>
  tasksApi
    .assignableUsers({ q: query, limit: PICKER_LIMIT })
    .then(({ data }) => data.results || data);

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
 * @param {{id: number, name: string}[]} [users] - Everyone assignable, when the caller already
 *   has the list. Omitted, the picker asks the server itself — only once it is opened, and
 *   filtered by what is typed in its search box (`?q=&limit=`).
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
  const searching = users === undefined;
  const [query, setQuery] = useState("");
  const [found, setFound] = useState(null);
  const [listError, setListError] = useState("");

  useEffect(() => {
    if (!open || !searching) return undefined;
    let live = true;
    // Typing is debounced; the first load on opening is not.
    const timer = setTimeout(() => {
      searchAssignableUsers(query.trim())
        .then((list) => { if (live) { setFound(list); setListError(""); } })
        .catch((err) => { if (live) setListError(getServerErrorMessage(err, "La liste des employés n'a pas pu être chargée. Réessayez.")); });
    }, query ? 250 : 0);
    return () => { live = false; clearTimeout(timer); };
  }, [open, searching, query]);
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
    } catch (err) {
      setError(getServerErrorMessage(err, "L'affectation n'a pas été enregistrée. Réessayez."));
    } finally {
      setSaving(false);
    }
  };

  const summary = assignedToNames.length === 0
    ? "Non assignée"
    : `Assignée à ${assignedToNames.join(", ")}`;
  const mine = currentUserId != null && assignedTo.includes(currentUserId);

  // In search mode the people already assigned stay listed (and untickable) even when the
  // current search would not return them.
  let candidates = users ?? [];
  if (searching) {
    const assigned = assignedTo.map((id, i) => ({ id, name: assignedToNames[i] ?? "" }));
    const rest = (found ?? []).filter((u) => !assignedTo.includes(u.id));
    candidates = [...assigned, ...rest];
  }

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
          {searching && (
            <label className="assignee-picker-search">
              <Search size={14} strokeWidth={1.9} aria-hidden="true" />
              <input
                type="search"
                value={query}
                placeholder="Rechercher"
                aria-label="Rechercher un employé"
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
          )}
          {listError && <p className="field-error" role="alert" style={{ margin: 0 }}>{listError}</p>}
          {searching && found === null ? (
            !listError && (
              <span className="assignee-picker-status">
                <Loader2 size={13} className="spin" /> Chargement…
              </span>
            )
          ) : candidates.length === 0 ? (
            <p className="empty-state" style={{ margin: 0 }}>
              {query.trim() ? "Aucun employé ne correspond." : "Aucun compte à assigner."}
            </p>
          ) : (
            candidates.map((candidate) => (
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
          {searching && found?.length === PICKER_LIMIT && (
            <p className="assignee-picker-hint">
              Seuls les {PICKER_LIMIT} premiers noms sont affichés — tapez un nom pour affiner.
            </p>
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
