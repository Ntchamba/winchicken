import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Minus, TrendingDown, TrendingUp } from "lucide-react";
import { financeApi } from "../../api/endpoints";
import { PERIOD_OPTIONS, PRODUCT_TYPE_LABELS } from "./labels";
import { formatMoney } from "../../utils/money";

const TREND_ICON = { up: TrendingUp, down: TrendingDown, flat: Minus };
const TREND_LABELS = { up: "Hausse", down: "Baisse", flat: "Stable" };

/**
 * "Ventes" section of the single-page Finances view (2026-08-27, Finances restructure Part B):
 * farm-wide sales evolution — bucketed chart + period toggle + large stat numbers. This is the
 * farm-wide aggregate; Caissier keeps their own full sales visibility via `/dashboard/cashier`
 * regardless of this section's access tier (unchanged, per the task's own spec).
 */
export default function VentesSection() {
  const [period, setPeriod] = useState("month");
  const [data, setData] = useState(null);

  useEffect(() => {
    financeApi.salesEvolution(period).then(({ data }) => setData(data));
  }, [period]);

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
          <p className="stat-label">Tendance des ventes</p>
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
            <Bar dataKey="total" fill="var(--mint)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="finance-grid">
        <div className="finance-stack">
          <div className="stat-card">
            <p className="stat-label">Chiffre d'affaires total</p>
            <p className="stat-value">{formatMoney(data.totalRevenue)}</p>
          </div>
          <div className="stat-card">
            <p className="stat-label">Nombre de ventes</p>
            <p className="stat-value">{data.salesCount.toLocaleString()}</p>
          </div>
        </div>
        <div className="finance-stack">
          {data.breakdown.map((b) => (
            <div className="stat-card" key={b.productType}>
              <p className="stat-label">{PRODUCT_TYPE_LABELS[b.productType] || b.productType}</p>
              <p className="stat-value">{formatMoney(b.amount)}</p>
            </div>
          ))}
          {data.breakdown.length === 0 && <p className="empty-state">Aucune vente sur cette période.</p>}
        </div>
      </div>
    </>
  );
}
