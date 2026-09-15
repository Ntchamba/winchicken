import { useCallback, useEffect, useState } from "react";
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
 * @param {string} houseCode
 * @param {number} [reloadKey] - Bump to refetch after an assignment changed elsewhere.
 * @param {() => void} [onChanged] - Called after a removal, so the caller can refetch tasksNow.
 */
export default function AssignmentsPanel({ houseCode, reloadKey, onChanged }) {
  const { user } = useAuth();
  const canAssign = CAN_ASSIGN_ROLES.includes(user.role);
  const [rows, setRows] = useState([]);
  const [removingId, setRemovingId] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    if (!canAssign) return;
    housesApi
      .assignments(houseCode)
      .then(({ data }) => setRows(data))
      .catch(() => setError("Impossible de charger les affectations."));
  }, [canAssign, houseCode]);

  useEffect(() => { load(); }, [load, reloadKey]);

  if (!canAssign) return null;

  const handleRemove = async (taskId) => {
    setRemovingId(taskId);
    setError("");
    try {
      await housesApi.assignTask(houseCode, taskId, null);
      setRows((current) => current.filter((row) => row.id !== taskId));
      onChanged?.();
    } catch {
      setError("Le retrait de l'affectation a échoué. Réessayez.");
    } finally {
      setRemovingId(null);
    }
  };

  // The heading lives here rather than in the page so that a role without assignment rights
  // sees no orphan title above nothing.
  return (
    <>
      <div className="section-row"><h2>Affectations en cours</h2></div>
      <div className="card schedule-card" style={{ marginBottom: 18 }}>
        {error && <p className="field-error">{error}</p>}
        {rows.length === 0 ? (
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
                  <span className="task-assignee-label">Assignée à {row.assignedToName}</span>
                  <p style={{ margin: "2px 0", fontSize: 12.5, color: "var(--muted)" }}>
                    {row.activeToday ? "Prévue aujourd'hui" : "Pas prévue aujourd'hui"}
                    {row.periodLabel ? ` — ${row.periodLabel}` : ""}
                  </p>
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
