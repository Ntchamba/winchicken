import { alertsApi } from "../../api/endpoints";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import "../../styles/dashboard-theme.css";
import QuickLinksBar from "../../components/QuickLinksBar";
import LoadMoreButton from "../../components/LoadMoreButton";
import usePagedList from "../../hooks/usePagedList";

// alert.status is the raw AlertStatus backend enum (NEW/SENT/RESOLVED) — displayed
// only through this French label map, never shown raw.
const ALERT_STATUS_LABELS = { NEW: "Nouvelle", SENT: "Envoyée", RESOLVED: "Résolue" };

// Newest first, 20 at a time; only the first 20 were ever reachable before (2026-09-25).
const fetchAlertsPage = (page) => alertsApi.listPage(page);

export default function AlertsListPage() {
  useDocumentTitle("Alertes");
  const { rows: alerts, count, hasMore, loading, error, loadMore } = usePagedList(fetchAlertsPage);

  return (
    <div className="page-wrap">
      <QuickLinksBar />
      <div className="breadcrumb">Tableau de bord / <strong>Alertes</strong></div>
      {error && <p className="field-error" role="alert">Les alertes n'ont pas pu être chargées.</p>}
      {alerts.length === 0 ? (
        !loading && !error && <p className="empty-state">Aucune alerte pour le moment.</p>
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
      <LoadMoreButton hasMore={hasMore} loading={loading} onClick={loadMore} shown={alerts.length} total={count} />
    </div>
  );
}
