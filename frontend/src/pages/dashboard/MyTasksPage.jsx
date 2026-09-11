import { useEffect, useState } from "react";
import { ClipboardCheck } from "lucide-react";
import { iconFor } from "../../components/HouseProtocolForm";
import { tasksApi } from "../../api/endpoints";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import "../../styles/dashboard-theme.css";
import QuickLinksBar from "../../components/QuickLinksBar";

/**
 * "Mes tâches" (2026-08-26, docs/deviations.md Part 15, Part E) — every task assigned to the
 * logged-in user, across every house, from `GET /api/tasks/mine/`
 * (`apps.houses.services.compute_tasks_now` run per house, filtered to this user — same
 * computation `TasksNowPanel` shows per-house, never a separate copy). Read-only: reassigning
 * happens from the per-house panel (`TasksNowPanel`), which is where the role check for who
 * *can* assign already lives.
 */
export default function MyTasksPage() {
  useDocumentTitle("Mes tâches");
  const [tasks, setTasks] = useState(null);

  useEffect(() => {
    tasksApi.mine().then(({ data }) => setTasks(data));
  }, []);

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
                <div key={`${task.houseCode}-${task.id}`} className="alert-item info">
                  <span className="alert-icon info"><Icon size={15} strokeWidth={1.8} /></span>
                  <div className="alert-text">
                    <p style={{ fontWeight: 600 }}>{task.category} — {task.what}</p>
                    {task.details && <p style={{ margin: "2px 0" }}>{task.details}</p>}
                    <span>
                      {task.houseName} ·{" "}
                      {task.recurrence
                        ? `Récurrent — ${task.recurrence.toLowerCase()}`
                        : task.periodLength
                          ? `Jour ${task.periodDay} sur ${task.periodLength}`
                          : `Jour ${task.periodDay} (jusqu'à la fin du cycle)`}
                    </span>
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
