import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Minus, TrendingDown, TrendingUp } from "lucide-react";
import { financeApi } from "../../api/endpoints";
import { EXPENSE_CATEGORY_LABELS, PERIOD_OPTIONS } from "./labels";
import { formatMoney } from "../../utils/money";

const TREND_ICON = { up: TrendingUp, down: TrendingDown, flat: Minus };
const TREND_LABELS = { up: "Hausse", down: "Baisse", flat: "Stable" };

/**
 * "Achats" section of the single-page Finances view (2026-08-27, Finances restructure Part C):
 * read-only aggregation of RECEIVED PurchaseOrder + Expense rows — no data entry here (that
 * happens in Stock's purchase-order flow and, for general expenses, the new "Enregistrer une
 * dépense" action added to /dashboard/cashier). Same access split as VentesSection.
 */
export default function AchatsSection({ refreshKey }) {
  const [period, setPeriod] = useState("month");
  const [data, setData] = useState(null);

  // `refreshKey` (bumped by SalairesSection after "Marquer comme payé" — see FinancesPage.jsx's
  // own docstring) forces a refetch when a LABOR expense was just created elsewhere on this
  // same-mounted page, which a hash-only navigation would otherwise never trigger.
  useEffect(() => {
    financeApi.purchasesEvolution(period).then(({ data }) => setData(data));
  }, [period, refreshKey]);

  const Toggle = (
    <div className="finance-toggle">
      {PERIOD_OPTIONS.map((opt) => (
        <button key={opt.value} className={period === opt.value ? "active" : ""} onClick={() => setPeriod(opt.value)}>
          {opt.label}
        </button>
      ))}
    </div>
  );

  if (!data) return <p className="empty-state">Chargement…</p>;

  if (data.access !== "full") {
    const TrendIcon = TREND_ICON[data.trend] || Minus;
    return (
      <>
        <div className="section-row">{Toggle}</div>
        <p className="empty-state" style={{ marginBottom: 18 }}>
          Vue restreinte — les montants sont réservés aux comptes Administrateur et Gérant de ferme.
        </p>
        <div className="stat-card" style={{ maxWidth: 260 }}>
          <p className="stat-label">Tendance des achats</p>
          <p className="stat-value" style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <TrendIcon size={22} />
            <span className={`badge-trend ${data.trend}`}>{TREND_LABELS[data.trend] || data.trend}</span>
          </p>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="section-row">{Toggle}</div>
      <div className="card schedule-card" style={{ height: 260, marginBottom: 18 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data.series}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
            <XAxis dataKey="bucket" fontSize={11} stroke="var(--muted)" />
            <YAxis fontSize={11} stroke="var(--muted)" />
            <Tooltip />
            <Bar dataKey="total" fill="var(--danger)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="finance-grid">
        <div className="finance-stack">
          <div className="stat-card">
            <p className="stat-label">Total dépensé</p>
            <p className="stat-value">{formatMoney(data.totalSpent)}</p>
          </div>
        </div>
        <div className="finance-stack">
          {data.breakdown.map((b) => (
            <div className="stat-card" key={b.category}>
              <p className="stat-label">{EXPENSE_CATEGORY_LABELS[b.category] || b.category}</p>
              <p className="stat-value">{formatMoney(b.amount)}</p>
            </div>
          ))}
          {data.breakdown.length === 0 && <p className="empty-state">Aucun achat sur cette période.</p>}
        </div>
      </div>
    </>
  );
}
