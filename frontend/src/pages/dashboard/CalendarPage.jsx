import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { scheduleApi } from "../../api/endpoints";
import { iconFor } from "../../components/HouseProtocolForm";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import "../../styles/dashboard-theme.css";
import "../../styles/calendar-page.css";
import QuickLinksBar from "../../components/QuickLinksBar";

const WEEKDAY_LABELS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
const CATEGORY_DOT = ["#0b8f68", "#2563eb", "#d6433f", "#7c3aed", "#b9790c"];
const VISIBLE_PER_DAY = 3;

function monthParam(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function dateKey(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function buildGrid(monthDate) {
  const year = monthDate.getFullYear();
  const month = monthDate.getMonth();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const leading = (new Date(year, month, 1).getDay() + 6) % 7; // Monday-first
  const days = [];
  for (let i = 0; i < leading; i += 1) days.push(null);
  for (let day = 1; day <= daysInMonth; day += 1) days.push(new Date(year, month, day));
  while (days.length % 7 !== 0) days.push(null);
  return days;
}

/**
 * Sidebar "Calendrier" month-grid view (2026-08-26) — reads /api/protocols/schedule/, which
 * (2026-08-27 bugfix) computes every ProtocolTemplate line due on each day of the month
 * directly (apps.houses.services.compute_month_schedule), the same day-in-range logic the
 * per-house "tâches à effectuer maintenant" panel uses — so a multi-day line (e.g. day 1-15)
 * now correctly appears on every one of those days, not just the first.
 */
export default function CalendarPage() {
  useDocumentTitle("Calendrier");

  const [monthDate, setMonthDate] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });
  const [entries, setEntries] = useState([]);
  const [expandedDay, setExpandedDay] = useState(null);

  useEffect(() => {
    scheduleApi.month(monthParam(monthDate)).then(({ data }) => setEntries(data));
  }, [monthDate]);

  const byDay = useMemo(() => {
    const map = {};
    for (const entry of entries) (map[entry.date] ||= []).push(entry);
    return map;
  }, [entries]);

  const days = useMemo(() => buildGrid(monthDate), [monthDate]);
  const monthLabel = monthDate.toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
  const today = dateKey(new Date());
  const expandedEntries = expandedDay ? byDay[expandedDay] || [] : [];

  const categoryColor = (category) => {
    const categories = [...new Set(entries.map((e) => e.category))];
    const index = categories.indexOf(category);
    return CATEGORY_DOT[index % CATEGORY_DOT.length] || "#5f7377";
  };

  return (
    <div className="page-wrap">
      <QuickLinksBar />
      <div className="breadcrumb">
        Tableau de bord / <strong>Calendrier</strong>
      </div>

      <div className="calendar-nav">
        <h1>{monthLabel}</h1>
        <div className="calendar-nav-buttons">
          <button
            aria-label="Mois précédent"
            onClick={() => setMonthDate((d) => new Date(d.getFullYear(), d.getMonth() - 1, 1))}
          >
            <ChevronLeft size={16} />
          </button>
          <button
            aria-label="Mois suivant"
            onClick={() => setMonthDate((d) => new Date(d.getFullYear(), d.getMonth() + 1, 1))}
          >
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      <div className="calendar-grid">
        {WEEKDAY_LABELS.map((label) => (
          <div key={label} className="calendar-weekday">
            {label}
          </div>
        ))}

        {days.map((day, index) => {
          if (!day) return <div key={`blank-${index}`} className="calendar-day blank" />;
          const key = dateKey(day);
          const dayEntries = byDay[key] || [];
          const visible = dayEntries.slice(0, VISIBLE_PER_DAY);
          const overflow = dayEntries.length - visible.length;
          return (
            <button
              key={key}
              type="button"
              className={`calendar-day ${dayEntries.length > 0 ? "has-tasks" : ""}`}
              onClick={() => dayEntries.length > 0 && setExpandedDay(key)}
            >
              <span className={`calendar-day-number ${key === today ? "today" : ""}`}>{day.getDate()}</span>
              {visible.map((entry) => (
                <span key={entry.id} className="calendar-task-pill">
                  <span className="calendar-task-dot" style={{ background: categoryColor(entry.category) }} />
                  {entry.startTime ? `${entry.startTime} · ` : ""}{entry.houseName} · {entry.what}
                </span>
              ))}
              {overflow > 0 && <span className="calendar-overflow">+{overflow}</span>}
            </button>
          );
        })}
      </div>

      {expandedDay && (
        <div
          style={{
            position: "fixed", inset: 0, zIndex: 70, display: "flex",
            alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,.4)",
          }}
        >
          <div className="card schedule-card" style={{ width: 420, maxWidth: "90vw", maxHeight: "80vh", overflowY: "auto" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
              <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: "#10242c" }}>
                {new Date(expandedDay).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" })}
              </h2>
              <button
                onClick={() => setExpandedDay(null)}
                aria-label="Fermer"
                style={{ border: 0, background: "none", color: "var(--muted)", cursor: "pointer", padding: 0 }}
              >
                <X size={18} />
              </button>
            </div>

            <div style={{ display: "grid", gap: 10 }}>
              {expandedEntries.map((entry) => {
                const Icon = iconFor(entry.icon);
                return (
                  <div key={entry.id} className="alert-item info" style={{ borderLeftColor: categoryColor(entry.category) }}>
                    <span className="alert-icon info">
                      <Icon size={15} strokeWidth={1.8} />
                    </span>
                    <div className="alert-text" style={{ flex: 1 }}>
                      <p style={{ fontWeight: 600 }}>
                        {entry.startTime && <span style={{ color: "var(--mint)" }}>{entry.startTime}–{entry.endTime} — </span>}
                        {entry.category} — {entry.what}
                      </p>
                      <span>
                        {entry.houseName} · {entry.batchName}
                      </span>
                      {entry.details && <p style={{ margin: "2px 0" }}>{entry.details}</p>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
