import { useCallback, useEffect, useState } from "react";
import { ClipboardCheck } from "lucide-react";
import { iconFor } from "../../components/HouseProtocolForm";
import { tasksApi } from "../../api/endpoints";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import "../../styles/dashboard-theme.css";
import QuickLinksBar from "../../components/QuickLinksBar";
import TaskCompleteButton from "../../components/TaskCompleteButton";

/**
 * "Mes tâches" (2026-08-26, docs/deviations.md Part 15, Part E) — every task assigned to the
 * logged-in user, across every house, from `GET /api/tasks/mine/`
 * (`apps.houses.services.compute_tasks_now` run per house, filtered to this user — same
 * computation `TasksNowPanel` shows per-house, never a separate copy). Read-only: reassigning
 * happens from the per-house panel (`TasksNowPanel`), which is where the role check for who
 * *can* assign already lives.
 *
 * Completing, however, belongs here: this is the screen a worker actually has open while
 * doing the round. A finished task stays in the list, struck through and marked "Fait", so
 * they can see what is already done today rather than watching rows disappear.
 */
export default function MyTasksPage() {
  useDocumentTitle("Mes tâches");
  const [tasks, setTasks] = useState(null);

  const load = useCallback(() => {
    tasksApi.mine().then(({ data }) => setTasks(data));
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="page-wrap">
      <QuickLinksBar />
      <div className="brand-row">
        <span className="brand-mark"><ClipboardCheck size={20} strokeWidth={1.8} /></span>
        <div>
          <p className="eyebrow">WINCHICKEN</p>
          <p className="brand-subtitle">Mes tâches</p>
        </div>
      </div>

      <div style={{ marginTop: 18 }}>
        {tasks === null ? (
          <p className="empty-state">Chargement…</p>
        ) : tasks.length === 0 ? (
          <p className="empty-state">Aucune tâche ne vous est assignée pour le moment.</p>
        ) : (
          <div className="alert-feed">
            {tasks.map((task) => {
              const Icon = iconFor(task.icon);
              return (
                <div
                  key={`${task.houseCode}-${task.id}-${task.timeSlotId ?? "all-day"}`}
                  className={`alert-item info${task.done ? " task-row--done" : ""}`}
                >
                  <span className="alert-icon info"><Icon size={15} strokeWidth={1.8} /></span>
                  <div className="alert-text">
                    <p style={{ fontWeight: 600 }}>{task.category} — {task.what}</p>
                    {task.details && <p style={{ margin: "2px 0" }}>{task.details}</p>}
                    <span>
                      {task.houseName} ·{" "}
                      {task.startTime && (
                        <strong className="task-slot-window">{task.startTime} – {task.endTime}</strong>
                      )}
                      {task.recurrence
                        ? `Récurrent — ${task.recurrence.toLowerCase()}`
                        : task.periodLength
                          ? `Jour ${task.periodDay} sur ${task.periodLength}`
                          : `Jour ${task.periodDay} (jusqu'à la fin du cycle)`}
                    </span>
                    {task.completable && (
                      <div style={{ marginTop: 10 }}>
                        <TaskCompleteButton
                          houseCode={task.houseCode}
                          taskId={task.id}
                          timeSlotId={task.timeSlotId}
                          done={task.done}
                          completedByName={task.completedByName}
                          onChanged={load}
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
    </div>
  );
}
