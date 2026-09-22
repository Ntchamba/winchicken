import { useEffect, useState } from "react";
import { ChevronRight, Clock } from "lucide-react";
import { tasksApi } from "../api/endpoints";
import { iconFor } from "./HouseProtocolForm";

/**
 * "Prochaines 48h" widget (2026-08-26, docs/deviations.md Part 16, Part C) — global view only.
 * Self-fetches `GET /api/tasks/upcoming/`, which is `apps.houses.services.
 * compute_cycle_milestones` (the same computation `CycleTimeline`'s per-house data comes from)
 * filtered to the next 48 hours across every house — not a separate calculation.
 *
 * @param {(path: string) => void} [onNavigate]
 */
export default function Upcoming48hWidget({ onNavigate }) {
  const [tasks, setTasks] = useState(null);

  useEffect(() => {
    tasksApi.upcoming().then(({ data }) => setTasks(data)).catch(() => setTasks([]));
  }, []);

  return (
    <div className="card schedule-card upcoming-48h-card">
      <div className="schedule-heading">
        <h2>Prochaines 48h</h2>
        <Clock size={16} strokeWidth={1.8} color="var(--muted)" />
      </div>
      {tasks === null ? (
        <p className="empty-state">Chargement…</p>
      ) : tasks.length === 0 ? (
        <p className="empty-state">Aucune tâche dans les 48 prochaines heures.</p>
      ) : (
        <div className="upcoming-48h-list">
          {tasks.map((t, i) => {
            const Icon = iconFor(t.icon);
            return (
              <div key={i} className="upcoming-48h-row">
                <span className="alert-icon info"><Icon size={14} strokeWidth={1.8} /></span>
                <div className="upcoming-48h-text">
                  <p>{t.category} — {t.what}</p>
                  <span>{t.houseName}{t.batchName ? ` · ${t.batchName}` : ""} · {t.when}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
      <button className="section-link" style={{ marginTop: 14 }} onClick={() => onNavigate?.("/dashboard/calendar")}>
        Voir le calendrier complet <ChevronRight size={14} strokeWidth={2} />
      </button>
    </div>
  );
}
