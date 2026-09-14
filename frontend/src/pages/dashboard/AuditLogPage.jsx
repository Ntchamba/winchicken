import { useEffect, useState } from "react";
import { FileClock } from "lucide-react";
import { auditLogApi } from "../../api/endpoints";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import "../../styles/dashboard-theme.css";
import QuickLinksBar from "../../components/QuickLinksBar";

// Kept in sync by hand with every apps.core.services.record_audit_log call site (see
// docs/deviations.md Part 15) — action is a short dotted code, never shown raw.
const ACTION_LABELS = {
  "batch.created": "Bande créée",
  "batch.updated": "Bande modifiée",
  "batch.deleted": "Bande supprimée",
  "batch.closed": "Bande clôturée",
  "protocol.updated": "Protocole modifié",
  "employee.created": "Employé créé",
  "employee.updated": "Employé modifié",
  "employee.deleted": "Employé supprimé",
  "stock.updated": "Stock mis à jour",
  "expense.created": "Dépense enregistrée",
  "sale.created": "Vente enregistrée",
  "purchase_order.created": "Commande fournisseur créée",
  "purchase_order.received": "Commande fournisseur reçue",
  "purchase_order.cancelled": "Commande fournisseur annulée",
  "farm.reset": "Réinitialisation de la ferme",
  "unusual_case.resolved": "Cas particulier résolu",
  "equipment_fault.resolved": "Panne d'équipement résolue",
};

/**
 * /dashboard/audit (2026-08-26, Administrateur only — docs/deviations.md Part 15) — paginated,
 * filterable read of `GET /api/audit-log/`. Server-side filtering (`?action=&date_from=&date_to=`,
 * `apps.core.views.AuditLogListView`) rather than client-side, since the table is meant to grow
 * unbounded over the farm's lifetime and DRF's default `PAGE_SIZE=20` pagination already caps
 * what any one request returns.
 */
export default function AuditLogPage() {
  useDocumentTitle("Journal d'audit");
  const [entries, setEntries] = useState([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [action, setAction] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    auditLogApi
      .list({ page, action: action || undefined, date_from: dateFrom || undefined, date_to: dateTo || undefined })
      .then(({ data }) => {
        setEntries(data.results || data);
        setCount(data.count ?? (data.results || data).length);
      })
      .finally(() => setLoading(false));
  }, [page, action, dateFrom, dateTo]);

  const pageSize = 20;
  const totalPages = Math.max(1, Math.ceil(count / pageSize));

  const handleFilterChange = (setter) => (e) => {
    setter(e.target.value);
    setPage(1);
  };

  return (
    <div className="page-wrap">
      <QuickLinksBar />
      <div className="brand-row">
        <span className="brand-mark"><FileClock size={20} strokeWidth={1.8} /></span>
        <div>
          <p className="eyebrow">WINCHICKEN</p>
          <p className="brand-subtitle">Journal d'audit</p>
        </div>
      </div>

      <div className="card house-card" style={{ marginTop: 18, marginBottom: 18 }}>
        <div className="detail-grid">
          <label className="field">
            <span>Type d'action</span>
            <select value={action} onChange={handleFilterChange(setAction)}>
              <option value="">Toutes</option>
              {Object.entries(ACTION_LABELS).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Du</span>
            <input type="date" value={dateFrom} onChange={handleFilterChange(setDateFrom)} />
          </label>
          <label className="field">
            <span>Au</span>
            <input type="date" value={dateTo} onChange={handleFilterChange(setDateTo)} />
          </label>
        </div>
      </div>

      {loading ? (
        <p className="empty-state">Chargement…</p>
      ) : entries.length === 0 ? (
        <p className="empty-state">Aucune entrée pour ces filtres.</p>
      ) : (
        <>
          <table className="data-table">
            <thead>
              <tr><th>Horodatage</th><th>Utilisateur</th><th>Action</th><th>Cible</th></tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id}>
                  <td>{new Date(entry.timestamp).toLocaleString()}</td>
                  <td>{entry.user_name_snapshot}</td>
                  <td>{ACTION_LABELS[entry.action] || entry.action}</td>
                  <td>{entry.target_description}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {totalPages > 1 && (
            <div className="pagination">
              <button onClick={() => setPage((p) => p - 1)} disabled={page <= 1}>Précédent</button>
              <span>Page {page} / {totalPages}</span>
              <button onClick={() => setPage((p) => p + 1)} disabled={page >= totalPages}>Suivant</button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
