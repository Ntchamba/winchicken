import { useEffect, useState } from "react";
import { payrollApi, employeesApi } from "../../api/endpoints";
import { getServerErrorMessage } from "../../api/errors";
import { formatMoney } from "../../utils/money";
import { useDateDefaultingToToday } from "../../hooks/useTodayISO";
import { fetchAllPages } from "../../api/pagination";
import usePagedList from "../../hooks/usePagedList";
import LoadMoreButton from "../LoadMoreButton";

// Payments grow every month, so they come 20 at a time; the employee list feeds a <select>
// and the hourly-rate table, which must hold everyone. Both read page 1 only before
// (2026-09-25): from the 21st employee on, hours could not be logged at all.
const fetchPaymentsPage = (page) => payrollApi.salaryPayments({ page });

const MONTH_LABELS = [
  "", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
  "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
];


/**
 * "Salaires" section of the single-page Finances view (2026-08-27, Finances restructure Part D).
 * Only ever rendered when the caller (FinancesPage) has already confirmed
 * user.role is ADMIN or FARM_MANAGER — server-side enforcement is the real gate
 * (SalaryPaymentListView/SalaryCalculateView/SalaryPaymentPayView/EmployeePayrollListView are all
 * IsAdminOrFarmManager), this component assumes it's only mounted for an allowed role.
 *
 * Also hosts hourly-rate editing for every employee. The task's own spec says rates are set
 * "from /dashboard/employees" — true for Admin, who already sees that page — but Farm Manager
 * has no visibility into /dashboard/employees at all (`canSeeEmployees` stays Admin/Secondary-
 * Admin only, unchanged elsewhere in this codebase). Rather than widen that page's access (which
 * would expose role/password/email editing Farm Manager isn't meant to touch), rate editing is
 * additionally surfaced right here — the one place both allowed roles already land. Backed by
 * the narrow `GET /api/employees/payroll/` + `PATCH /api/employees/{id}/hourly-rate/` endpoints.
 *
 * Also hosts the on-behalf-of hours entry the task's Part D asks for ("Administrateur and Gérant
 * de ferme can also add/edit WorkHoursEntry rows on behalf of any employee") — `MyHoursShortcut`
 * in the sidebar only ever self-reports (posts with no `user`), so this is the one place that
 * form exists, posting `POST /api/work-hours/` with an explicit `user` id.
 */
export default function SalairesSection({ onPaymentRecorded }) {
  const paymentList = usePagedList(fetchPaymentsPage);
  const payments = paymentList.rows;
  const [employees, setEmployees] = useState([]);
  const [rateEdits, setRateEdits] = useState({});
  const [calculating, setCalculating] = useState(false);
  const [error, setError] = useState("");
  const [savingRateId, setSavingRateId] = useState(null);
  const [payingId, setPayingId] = useState(null);
  // The date lives outside `hoursForm` so it can follow the farm-local day on its own — see
  // useTodayISO. The rest of the form is unrelated to the clock.
  const [hoursDate, setHoursDate, today] = useDateDefaultingToToday();
  const [hoursForm, setHoursForm] = useState({ user: "", hours_worked: "", note: "" });
  const [savingHours, setSavingHours] = useState(false);
  const [hoursSaved, setHoursSaved] = useState(false);

  const loadPayments = () => paymentList.reload();
  const loadEmployees = () => fetchAllPages(employeesApi.payrollList).then(setEmployees);

  useEffect(() => { loadEmployees(); }, []);

  const calculate = async () => {
    setCalculating(true);
    setError("");
    try {
      await payrollApi.calculateSalaries();
      await loadPayments();
    } catch (err) {
      setError(getServerErrorMessage(err, "Impossible de calculer les salaires."));
    } finally {
      setCalculating(false);
    }
  };

  const markPaid = async (id) => {
    setPayingId(id);
    setError("");
    try {
      const { data: paid } = await payrollApi.markPaid(id);
      // Replaced in place: reloading would fold the pages already opened back to the first 20.
      paymentList.setRows((rows) => rows.map((p) => (p.id === id ? { ...p, ...paid } : p)));
      // Marking paid just created a LABOR Expense (see SalaryPaymentPayView) — Achats/Globale,
      // already mounted and fetched on this same page, need to know to refetch.
      onPaymentRecorded?.();
    } catch (err) {
      setError(getServerErrorMessage(err, "Impossible de marquer ce paiement comme payé."));
    } finally {
      setPayingId(null);
    }
  };

  const saveRate = async (employeeId) => {
    const raw = rateEdits[employeeId];
    setSavingRateId(employeeId);
    setError("");
    try {
      await employeesApi.setHourlyRate(employeeId, raw === "" ? null : raw);
      await loadEmployees();
      setRateEdits((prev) => { const next = { ...prev }; delete next[employeeId]; return next; });
    } catch (err) {
      setError(getServerErrorMessage(err, "Impossible d'enregistrer ce taux horaire."));
    } finally {
      setSavingRateId(null);
    }
  };

  const logHoursForEmployee = async () => {
    if (!hoursForm.user || !hoursForm.hours_worked) return;
    setSavingHours(true);
    setError("");
    setHoursSaved(false);
    try {
      await payrollApi.logHours({
        user: hoursForm.user, date: hoursDate, hours_worked: hoursForm.hours_worked, note: hoursForm.note,
      });
      setHoursForm({ ...hoursForm, hours_worked: "", note: "" });
      setHoursSaved(true);
    } catch (err) {
      setError(getServerErrorMessage(err, "Impossible d'enregistrer ces heures."));
    } finally {
      setSavingHours(false);
    }
  };

  return (
    <>
      {error && <p className="field-error" style={{ marginBottom: 14 }}>{error}</p>}

      <div className="section-row">
        <h2>Enregistrer des heures pour un employé</h2>
      </div>
      <div className="card schedule-card" style={{ marginBottom: 22 }}>
        <div className="detail-grid">
          <label className="field">
            <span>Employé</span>
            <select value={hoursForm.user} onChange={(e) => setHoursForm({ ...hoursForm, user: e.target.value })}>
              <option value="">— Choisir —</option>
              {employees.map((emp) => <option key={emp.id} value={emp.id}>{emp.name}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Date</span>
            <input type="date" value={hoursDate} max={today} onChange={(e) => setHoursDate(e.target.value)} />
          </label>
          <label className="field">
            <span>Heures travaillées</span>
            <input type="number" min="0" step="0.25" value={hoursForm.hours_worked} onChange={(e) => setHoursForm({ ...hoursForm, hours_worked: e.target.value })} />
          </label>
        </div>
        <label className="field" style={{ marginTop: 14 }}>
          <span>Note (optionnel)</span>
          <input value={hoursForm.note} onChange={(e) => setHoursForm({ ...hoursForm, note: e.target.value })} placeholder="ex. Astreinte week-end" />
        </label>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 14, marginTop: 16 }}>
          {hoursSaved && <p style={{ margin: 0, color: "var(--mint)", fontSize: 13 }}>Heures enregistrées.</p>}
          <button className="save-button" disabled={savingHours} onClick={logHoursForEmployee}>
            {savingHours ? "…" : "Enregistrer les heures"}
          </button>
        </div>
      </div>

      <div className="section-row">
        <h2>Taux horaires</h2>
      </div>
      <div className="card schedule-card" style={{ marginBottom: 22 }}>
        <table className="data-table stacked">
          <thead>
            <tr><th>Employé</th><th>Taux horaire</th><th></th></tr>
          </thead>
          <tbody>
            {employees.map((emp) => {
              const editing = rateEdits[emp.id] !== undefined;
              const value = editing ? rateEdits[emp.id] : (emp.hourly_rate ?? "");
              return (
                <tr key={emp.id}>
                  <td data-label="Employé">{emp.name}</td>
                  <td data-label="Taux horaire">
                    <input
                      type="number" min="0" step="0.01" value={value}
                      style={{ width: 100, padding: "4px 8px", borderRadius: 8, border: "1px solid var(--line)" }}
                      onChange={(e) => setRateEdits((prev) => ({ ...prev, [emp.id]: e.target.value }))}
                    />
                  </td>
                  <td>
                    {editing && (
                      <button className="save-button" style={{ padding: "5px 12px" }} disabled={savingRateId === emp.id} onClick={() => saveRate(emp.id)}>
                        {savingRateId === emp.id ? "…" : "Enregistrer"}
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {employees.length === 0 && <p className="empty-state">Aucun employé.</p>}
      </div>

      <div className="section-row">
        <h2>Salaires</h2>
        <button className="save-button" style={{ padding: "8px 16px" }} disabled={calculating} onClick={calculate}>
          {calculating ? "Calcul…" : "Calculer les salaires du mois"}
        </button>
      </div>
      <div className="card schedule-card">
        <table className="data-table stacked">
          <thead>
            <tr><th>Employé</th><th>Période</th><th>Heures</th><th>Montant</th><th>Statut</th><th></th></tr>
          </thead>
          <tbody>
            {payments.map((p) => (
              <tr key={p.id}>
                <td data-label="Employé">{p.employeeName}</td>
                <td data-label="Période">{MONTH_LABELS[p.period_month]} {p.period_year}</td>
                <td data-label="Heures">{p.total_hours}</td>
                <td data-label="Montant">{formatMoney(p.amount)}</td>
                <td data-label="Statut">
                  <span className={`status-pill ${p.status === "PAID" ? "received" : "pending"}`}>
                    {p.status === "PAID" ? "Payé" : "À payer"}
                  </span>
                </td>
                <td>
                  {p.status === "PENDING" && (
                    <button className="save-button" style={{ padding: "5px 12px" }} disabled={payingId === p.id} onClick={() => markPaid(p.id)}>
                      {payingId === p.id ? "…" : "Marquer comme payé"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {payments.length === 0 && !paymentList.loading && <p className="empty-state">Aucun salaire calculé pour le moment.</p>}
        <LoadMoreButton
          hasMore={paymentList.hasMore}
          loading={paymentList.loading}
          onClick={paymentList.loadMore}
          shown={payments.length}
          total={paymentList.count}
        />
      </div>
    </>
  );
}
