import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Bell, Info, Loader2 } from "lucide-react";
import { alertsApi } from "../api/endpoints";

// alert.ruleType is the raw AlertRuleType backend enum — displayed only through this French
// label map, matching AlertsListPage.jsx's ALERT_STATUS_LABELS convention (never shown raw).
const RULE_TYPE_LABELS = {
  LOW_STOCK: "Stock bas",
  VACCINE_DUE: "Vaccin à venir",
  CONSUMPTION_DEVIATION: "Écart de consommation",
  PROFITABILITY_THRESHOLD: "Seuil de rentabilité",
  SANITARY_VOID_END: "Fin de vide sanitaire",
  PROTOCOL_TASK: "Tâche du protocole",
  WEIGHING_REMINDER: "Rappel de pesée",
};

const SEVERITY_ICON = { danger: AlertTriangle, warning: AlertTriangle, info: Info };

function timeAgo(isoDate) {
  const diffMin = Math.round((Date.now() - new Date(isoDate).getTime()) / 60000);
  if (diffMin < 1) return "à l'instant";
  if (diffMin < 60) return `il y a ${diffMin} min`;
  const diffH = Math.round(diffMin / 60);
  if (diffH < 24) return `il y a ${diffH} h`;
  return `il y a ${Math.round(diffH / 24)} j`;
}

/**
 * Sidebar notification bell (2026-08-26) — badge count comes from the parent's shared
 * `useSidebarNotifications` refetch (see DashboardShellContent), so it stays in sync with the
 * Stock/Finance badges on the same trigger. The dropdown's own alert list is fetched lazily,
 * only when opened.
 *
 * @param {number} unreadCount
 * @param {() => void} onCountsChanged - Called after mark-read/mark-all-read so the parent can
 *   refetch the shared badge counts.
 */
export default function NotificationBell({ unreadCount, onCountsChanged }) {
  const [open, setOpen] = useState(false);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    alertsApi.list().then(({ data }) => setAlerts(data.results || data)).finally(() => setLoading(false));
  }, [open]);

  useEffect(() => {
    function onClickOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const markRead = async (id) => {
    await alertsApi.markRead(id);
    setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, is_read: true } : a)));
    onCountsChanged?.();
  };

  const markAllRead = async () => {
    await alertsApi.markAllRead();
    setAlerts((prev) => prev.map((a) => ({ ...a, is_read: true })));
    onCountsChanged?.();
  };

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button className="notification-bell" onClick={() => setOpen((v) => !v)} aria-label="Notifications">
        <Bell size={16} strokeWidth={1.8} />
        {unreadCount > 0 && <span className="notification-bell-badge pulse-alert">{unreadCount > 9 ? "9+" : unreadCount}</span>}
      </button>

      {open && (
        <div className="notification-panel">
          <div className="notification-panel-header">
            <h4>Notifications</h4>
            <button onClick={markAllRead}>Tout marquer comme lu</button>
          </div>

          {loading && (
            <p className="notification-empty">
              <Loader2 size={16} className="spin" />
            </p>
          )}
          {!loading && alerts.length === 0 && <p className="notification-empty">Aucune notification.</p>}
          {!loading &&
            alerts.map((alert) => {
              const Icon = SEVERITY_ICON[alert.severity] || Info;
              return (
                <div key={alert.id} className={`notification-row ${alert.is_read ? "read" : ""}`}>
                  <Icon size={16} className={`notification-row-icon ${alert.severity}`} style={{ marginTop: 2 }} />
                  <div className="notification-row-text">
                    <p>{alert.message}</p>
                    <span>
                      {RULE_TYPE_LABELS[alert.ruleType] || alert.ruleType}
                      {alert.houseName ? ` · ${alert.houseName}` : ""}
                      {alert.batchName ? ` · ${alert.batchName}` : ""} · {timeAgo(alert.triggered_at)}
                    </span>
                  </div>
                  {!alert.is_read && (
                    <button className="notification-row-mark" onClick={() => markRead(alert.id)}>
                      Marquer comme lu
                    </button>
                  )}
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
}
