import { useCallback, useEffect, useState } from "react";
import { getServerErrorMessage } from "../api/errors";
import AssigneePicker from "./AssigneePicker";
import { housesApi } from "../api/endpoints";
// Reuses the secondary-button style TaskCompleteButton already defines (44px touch target)
// rather than growing a second copy of it.
import "./task-complete-button.css";
import { useAuth } from "../context/AuthContext";

// Same role set as CanEditHouseProtocol server-side, like TasksNowPanel's copy — the endpoint
// itself is the authority, this only decides whether the card is worth rendering.
const CAN_ASSIGN_ROLES = ["ADMIN", "FARM_MANAGER", "FARMER"];

/**
 * "Affectations en cours" card (2026-09-16, FIX 4) — every assignment the house currently
 * carries, including the ones whose task is not due today.
 *
 * `TasksNowPanel` can only ever show assignments on tasks due *now*, so the day after a weekly
 * weighing the assignment left the screen while `assigned_to` stayed in the database: nothing
 * could see it and nothing could clear it. This card is the wider view — `activeToday: false`
 * rows are marked "Pas prévue aujourd'hui" rather than hidden, and each row can be cleared
 * through the same assign endpoint the panel uses.
 *
 * Since FIX 7 (2026-09-16) a line carries several assignees, so this card edits the set with
 * the same `AssigneePicker` `TasksNowPanel` uses — for a task that is not due today this is
 * the *only* screen that can add someone to it, which is exactly the gap FIX 4 found. The
 * "Retirer" button stays as the one-tap "nobody is on this any more" (`[]`).
 *
 * @param {string} houseCode
 * @param {number} [reloadKey] - Bump to refetch after an assignment changed elsewhere.
 * @param {() => void} [onChanged] - Called after a removal, so the caller can refetch tasksNow.
 */
export default function AssignmentsPanel({ houseCode, reloadKey, onChanged }) {
  const { user } = useAuth();
  const canAssign = CAN_ASSIGN_ROLES.includes(user.role);
  const [rows, setRows] = useState([]);
  const [removingId, setRemovingId] = useState(null);
  // An empty list means "none" only once it has loaded (it used to say so while loading).
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    if (!canAssign) return;
    housesApi
      .assignments(houseCode)
      .then(({ data }) => { setRows(data); setLoaded(true); })
      .catch((err) => setError(getServerErrorMessage(err, "Les affectations n'ont pas pu être chargées. Réessayez.")));
  }, [canAssign, houseCode]);

  useEffect(() => { load(); }, [load, reloadKey]);

  if (!canAssign) return null;

  const handleRemove = async (taskId) => {
    setRemovingId(taskId);
    setError("");
    try {
      await housesApi.assignTask(houseCode, taskId, []);
      setRows((current) => current.filter((row) => row.id !== taskId));
      onChanged?.();
    } catch (err) {
      setError(getServerErrorMessage(err, "Le retrait de l'affectation a échoué. Réessayez."));
    } finally {
      setRemovingId(null);
    }
  };

  // Re-reads from the server rather than patching `rows` locally: an emptied set must drop the
  // row, and the server is the only thing that decides what this list holds.
  const handleAssign = async (taskId, assigneeIds) => {
    await housesApi.assignTask(houseCode, taskId, assigneeIds);
    load();
    onChanged?.();
  };

  // The heading lives here rather than in the page so that a role without assignment rights
  // sees no orphan title above nothing.
  return (
    <>
      <div className="section-row"><h2>Affectations en cours</h2></div>
      <div className="card schedule-card" style={{ marginBottom: 18 }}>
        {error && <p className="field-error">{error}</p>}
        {!loaded && !error ? (
          <p className="empty-state">Chargement des affectations…</p>
        ) : rows.length === 0 ? (
          <p className="empty-state">Aucune tâche affectée dans ce bâtiment.</p>
        ) : (
          <div style={{ display: "grid", gap: 10 }}>
            {rows.map((row) => (
              <div
                key={row.id}
                className="alert-item info"
                style={{ borderLeftColor: row.activeToday ? "var(--mint)" : "var(--muted)" }}
              >
                <div className="alert-text" style={{ flex: 1 }}>
                  <p style={{ fontWeight: 600 }}>{row.category} — {row.what}</p>
                  <p style={{ margin: "2px 0", fontSize: 12.5, color: "var(--muted)" }}>
                    {row.activeToday ? "Prévue aujourd'hui" : "Pas prévue aujourd'hui"}
                    {row.periodLabel ? ` — ${row.periodLabel}` : ""}
                  </p>
                  <AssigneePicker
                    assignedTo={row.assignedTo ?? []}
                    assignedToNames={row.assignedToNames ?? []}
                    currentUserId={user.id}
                    disabled={removingId === row.id}
                    onChange={(ids) => handleAssign(row.id, ids)}
                  />
                </div>
                <button
                  type="button"
                  className="task-undo-button"
                  disabled={removingId === row.id}
                  onClick={() => handleRemove(row.id)}
                >
                  {removingId === row.id ? "Retrait…" : "Retirer"}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
