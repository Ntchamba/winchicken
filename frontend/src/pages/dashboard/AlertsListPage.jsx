import { useEffect, useState } from "react";
import { alertsApi } from "../../api/endpoints";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import "../../styles/dashboard-theme.css";
import QuickLinksBar from "../../components/QuickLinksBar";

// alert.status is the raw AlertStatus backend enum (NEW/SENT/RESOLVED) — displayed
// only through this French label map, never shown raw.
const ALERT_STATUS_LABELS = { NEW: "Nouvelle", SENT: "Envoyée", RESOLVED: "Résolue" };

export default function AlertsListPage() {
  useDocumentTitle("Alertes");
  const [alerts, setAlerts] = useState([]);

  useEffect(() => {
    alertsApi.list().then(({ data }) => setAlerts(data.results || data));
  }, []);

  return (
    <div className="page-wrap">
      <QuickLinksBar />
      <div className="breadcrumb">Tableau de bord / <strong>Alertes</strong></div>
      {alerts.length === 0 ? (
        <p className="empty-state">Aucune alerte pour le moment.</p>
      ) : (
        <div className="alert-feed">
          {alerts.map((alert) => (
            <div key={alert.id} className={`alert-item ${alert.severity}`}>
              <div className="alert-text">
                <p>{alert.message}</p>
                <span>{new Date(alert.triggered_at).toLocaleString()} · {ALERT_STATUS_LABELS[alert.status] || alert.status}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
