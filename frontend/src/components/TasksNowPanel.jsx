import { useEffect, useState } from "react";
import { iconFor } from "./HouseProtocolForm";
import AssigneePicker from "./AssigneePicker";
import TaskCompleteButton from "./TaskCompleteButton";
import { housesApi, tasksApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";

// Section 8 permission matrix: same role set as CanEditHouseProtocol server-side
// (apps.core.permissions) — kept in sync by hand, matching this project's existing pattern for
// role-gated UI (e.g. DashboardShell's canManageHouses/canSeeEmployees).
const CAN_ASSIGN_ROLES = ["ADMIN", "FARM_MANAGER", "FARMER"];

/**
 * "Tâches à effectuer maintenant" card — extracted from `HouseDetailPage` (2026-08-25) as its
 * own presentational piece, per this project's "no mega-components" convention.
 *
 * Task assignment (2026-08-26, docs/deviations.md Part 15): Admin/Farm Manager/Farmer get an
 * assignee `<select>` per task (`PATCH /api/houses/{houseCode}/tasks-now/{taskId}/assign/`,
 * refetches via `onAssigned` on change — same "call the parent's reload" discipline as the
 * rest of this app, not local-only state that could drift from the server). Every other role
 * sees a read-only "Assignée à {name}" label instead, with their own assigned tasks visually
 * highlighted (`task-assigned-mine`).
 *
 * Assignee options (2026-08-27 bugfix, docs/deviations.md): come from
 * `GET /api/tasks/assignable-users/`, not `/api/employees/` — that endpoint is Admin/Secondary-
 * Admin-only (403'd a Farm Manager/Farmer doing the assigning) and excludes the requester's own
 * account (so Admin could never assign a task to themselves). Every farm user, every role,
 * including whoever is currently logged in, can be *chosen* as an assignee — who can *perform*
 * an assignment is still `CAN_ASSIGN_ROLES` below, unchanged.
 *
 * Several assignees per line since 2026-09-16 (FIX 7): the `<select>` became the shared
 * `AssigneePicker`, and `assignedTo`/`assignedToNames` are parallel lists. One worker
 * completing an occurrence closes it for all of them — completion is a property of the task
 * (the feed either got distributed or it did not), not of each assignee.
 *
 * @param {{dayOfCycle: ?number, tasks: {id: string, category: string, icon: string, what: string, details: string, periodDay: ?number, periodLength: ?number, recurrence: ?string, assignedTo: number[], assignedToNames: string[]}[]}} tasksNow
 * @param {string} [houseCode] - Required for assignment (omit to render read-only, e.g. if ever reused somewhere without edit rights).
 * @param {() => void} [onAssigned] - Called after a successful assignment change, to refetch tasksNow.
 */
export default function TasksNowPanel({ tasksNow, houseCode, onAssigned }) {
  const { user } = useAuth();
  const canAssign = houseCode && CAN_ASSIGN_ROLES.includes(user.role);
  const [employees, setEmployees] = useState([]);
  const [savingId, setSavingId] = useState(null);

  useEffect(() => {
    if (!canAssign) return;
    tasksApi.assignableUsers().then(({ data }) => setEmployees(data.results || data));
  }, [canAssign]);

  // Takes the whole set: the endpoint `set()`s it, so what the picker shows is what is sent.
  // Errors are surfaced by `AssigneePicker` itself, which is why this re-throws instead of
  // swallowing — a failed assignment that looks like a successful one is the FIX 6 failure.
  const handleAssign = async (taskId, assigneeIds) => {
    setSavingId(taskId);
    try {
      await housesApi.assignTask(houseCode, taskId, assigneeIds);
      onAssigned?.();
    } finally {
      setSavingId(null);
    }
  };

  return (
    <div className="card schedule-card" style={{ marginBottom: 18 }}>
      {tasksNow.dayOfCycle != null && (
        <p style={{ margin: "0 0 12px", fontSize: 12.5, color: "var(--muted)" }}>Jour {tasksNow.dayOfCycle} du cycle</p>
      )}
      {tasksNow.tasks.length === 0 ? (
        <p className="empty-state">Aucune tâche prévue pour aujourd'hui.</p>
      ) : (
        <div style={{ display: "grid", gap: 10 }}>
          {tasksNow.tasks.map((task) => {
            const Icon = iconFor(task.icon);
            const assignedTo = task.assignedTo ?? [];
            const assignedToNames = task.assignedToNames ?? [];
            const isMine = assignedTo.includes(user.id);
            return (
              <div
                key={`${task.id}-${task.timeSlotId ?? "all-day"}`}
                className={`alert-item info${isMine ? " task-assigned-mine" : ""}${task.done ? " task-row--done" : ""}`}
                style={{ borderLeftColor: isMine ? "var(--mint-fill)" : "var(--mint)" }}
              >
                <span className="alert-icon info"><Icon size={15} strokeWidth={1.8} /></span>
                <div className="alert-text" style={{ flex: 1 }}>
                  <p style={{ fontWeight: 600 }}>{task.category} — {task.what}</p>
                  {task.details && <p style={{ margin: "2px 0" }}>{task.details}</p>}
                  <span>
                    {task.startTime && (
                      <strong className="task-slot-window">{task.startTime} – {task.endTime}</strong>
                    )}
                    {task.recurrence
                      ? `Récurrent — ${task.recurrence.toLowerCase()}`
                      : task.periodLength
                        ? `Jour ${task.periodDay} sur ${task.periodLength}`
                        : `Jour ${task.periodDay} (jusqu'à la fin du cycle)`}
                  </span>
                  {/* Assignment lives on the ProtocolTemplate, not the occurrence, so every
                      slot of a line shows — and changes — the same assignees. */}
                  <div style={{ marginTop: 6 }}>
                    {canAssign ? (
                      <AssigneePicker
                        users={employees}
                        assignedTo={assignedTo}
                        assignedToNames={assignedToNames}
                        currentUserId={user.id}
                        disabled={savingId === task.id}
                        onChange={(ids) => handleAssign(task.id, ids)}
                      />
                    ) : (
                      assignedToNames.length > 0 && (
                        <span className="task-assignee-label">
                          Assignée à {assignedToNames.join(", ")}{isMine ? " (vous)" : ""}
                        </span>
                      )
                    )}
                  </div>
                  {task.completable && (
                    <div style={{ marginTop: 10 }}>
                      <TaskCompleteButton
                        houseCode={houseCode}
                        taskId={task.id}
                        timeSlotId={task.timeSlotId}
                        done={task.done}
                        completedByName={task.completedByName}
                        onChanged={onAssigned}
                      />
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
