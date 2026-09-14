import { useEffect, useState } from "react";
import { iconFor } from "./HouseProtocolForm";
import { housesApi } from "../api/endpoints";

/**
 * Cycle timeline with milestone ticks (2026-08-26, docs/deviations.md Part 16, Part B) —
 * per-house view, extends the simple "Jour X sur Y" text already shown in the house header
 * (`HouseDetailPage.jsx`'s own `<p className="schedule-note">`, untouched) with a horizontal
 * timeline: start/current/end markers plus a tick per upcoming `ProtocolTemplate`-derived
 * milestone, positioned by day-of-cycle. Self-fetches `GET /api/houses/{houseCode}/
 * milestones/` (`apps.houses.services.compute_cycle_milestones` — the same computation
 * `Upcoming48hWidget` filters for its global 48h view).
 *
 * Tooltip is click/hover-toggled, not a native `title` attribute — `title` alone doesn't work
 * well for tap-to-open on touch devices, and the task explicitly asks for "hovering/tapping."
 *
 * @param {string} houseCode
 */
export default function CycleTimeline({ houseCode }) {
  const [data, setData] = useState(null);
  const [openId, setOpenId] = useState(null);

  useEffect(() => {
    if (!houseCode) return;
    setData(null);
    housesApi.milestones(houseCode).then(({ data }) => setData(data)).catch(() => setData({ milestones: [] }));
  }, [houseCode]);

  if (!data || data.dayOfCycle == null || !data.cycleLength) return null;

  const { cycleLength, dayOfCycle, milestones } = data;
  const pct = (day) => Math.min(100, Math.max(0, (day / cycleLength) * 100));

  return (
    <div className="card schedule-card cycle-timeline-card">
      <p className="schedule-note" style={{ marginBottom: 18 }}>Jour {dayOfCycle} sur {cycleLength}</p>
      <div className="cycle-timeline-track">
        <div className="cycle-timeline-fill" style={{ width: `${pct(dayOfCycle)}%` }} />
        <div className="cycle-timeline-endpoint" style={{ left: 0 }} />
        <div className="cycle-timeline-endpoint cycle-timeline-current" style={{ left: `${pct(dayOfCycle)}%` }} />
        <div className="cycle-timeline-endpoint" style={{ left: "100%" }} />
        {milestones.map((m) => {
          const Icon = iconFor(m.icon);
          const open = openId === m.id;
          return (
            <button
              key={m.id}
              type="button"
              className={`cycle-timeline-tick ${m.isPast ? "cycle-timeline-tick-past" : "cycle-timeline-tick-upcoming"}`}
              style={{ left: `${pct(m.day)}%` }}
              onMouseEnter={() => setOpenId(m.id)}
              onMouseLeave={() => setOpenId((cur) => (cur === m.id ? null : cur))}
              onClick={() => setOpenId((cur) => (cur === m.id ? null : m.id))}
              aria-label={`${m.category} — ${m.what} — jour ${m.day}`}
            >
              <Icon size={11} strokeWidth={2.2} />
              {open && (
                <div className="cycle-timeline-tooltip">
                  <strong>{m.category}</strong>
                  <span>{m.what}</span>
                  <span>Jour {m.day}</span>
                </div>
              )}
            </button>
          );
        })}
      </div>
      <div className="cycle-timeline-labels">
        <span>Début</span>
        <span>Fin de cycle</span>
      </div>
    </div>
  );
}
