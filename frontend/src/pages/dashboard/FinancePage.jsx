import { useEffect, useState } from "react";
import { Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Minus, TrendingDown, TrendingUp } from "lucide-react";
import { financeApi } from "../../api/endpoints";
import "../../styles/dashboard-theme.css";

const CATEGORY_COLORS = {
  FEED: "#0b8f68", LABOR: "#17b892", VETERINARY: "#5f7377", DEPRECIATION: "#b9790c", MISC: "#d6433f",
};

// row.category (transactions table) is the raw ExpenseCategory/ProductType backend enum —
// displayed only through this French label map, never shown raw.
const CATEGORY_LABELS = {
  FEED: "Aliment", VETERINARY: "Vétérinaire", MISC: "Divers", DEPRECIATION: "Amortissement", LABOR: "Main-d'œuvre",
  BIRD: "Volaille", EGG: "Œufs", CULL: "Réforme", MANURE: "Fumier",
};

const TREND_ICON = { up: TrendingUp, down: TrendingDown, flat: Minus };
const TREND_LABELS = { up: "Hausse", down: "Baisse", flat: "Stable" };

export default function FinancePage() {
  const [range, setRange] = useState("6m");
  const [summary, setSummary] = useState(null);
  const [categories, setCategories] = useState([]);
  const [transactions, setTransactions] = useState({ count: 0, page: 1, results: [] });
  const [typeFilter, setTypeFilter] = useState("all");

  useEffect(() => {
    financeApi.summary(range).then(({ data }) => setSummary(data));
  }, [range]);

  const isFull = summary?.access === "full";

  // Only the full-access role fetches the exact-figure endpoints — the API 403s a
  // restricted role on both anyway (server-enforced), this just avoids the request.
  useEffect(() => {
    if (!isFull) return;
    financeApi.expenseCategories(range).then(({ data }) => setCategories(data.categories));
  }, [range, isFull]);

  const loadTransactions = (page) => {
    financeApi.transactions(page, typeFilter).then(({ data }) => setTransactions(data));
  };

  useEffect(() => { if (isFull) loadTransactions(1); }, [typeFilter, isFull]);

  if (!summary) return <div className="page-wrap"><p className="empty-state">Chargement…</p></div>;

  if (!isFull) {
    const RevenueIcon = TREND_ICON[summary.revenueTrend] || Minus;
    const ExpenseIcon = TREND_ICON[summary.expenseTrend] || Minus;
    return (
      <div className="page-wrap">
        <div className="breadcrumb">Tableau de bord / <strong>Finance</strong></div>
        <p className="empty-state" style={{ marginBottom: 18 }}>
          Vue restreinte — les montants et le journal des transactions sont réservés aux comptes Administrateur et Gérant de ferme.
        </p>
        <div className="finance-stack" style={{ maxWidth: 420 }}>
          <div className="stat-card">
            <p className="stat-label">Tendance du chiffre d'affaires</p>
            <p className="stat-value" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <RevenueIcon size={22} />
              <span className={`badge-trend ${summary.revenueTrend}`}>{TREND_LABELS[summary.revenueTrend] || summary.revenueTrend}</span>
            </p>
          </div>
          <div className="stat-card">
            <p className="stat-label">Tendance des charges</p>
            <p className="stat-value" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <ExpenseIcon size={22} />
              <span className={`badge-trend ${summary.expenseTrend}`}>{TREND_LABELS[summary.expenseTrend] || summary.expenseTrend}</span>
            </p>
          </div>
        </div>
      </div>
    );
  }

  const totalPages = Math.max(1, Math.ceil(transactions.count / (transactions.pageSize || 20)));
  const thisMonth = summary.months[summary.months.length - 1] || { revenue: 0, expenses: 0 };

  return (
    <div className="page-wrap">
      <div className="breadcrumb">Tableau de bord / <strong>Finance</strong></div>

      <div className="section-row">
        <h2>Chiffre d'affaires vs charges d'exploitation</h2>
        <div className="finance-toggle">
          <button className={range === "6m" ? "active" : ""} onClick={() => setRange("6m")}>6M</button>
          <button className={range === "1y" ? "active" : ""} onClick={() => setRange("1y")}>1A</button>
        </div>
      </div>
      <div className="card schedule-card" style={{ height: 260, marginBottom: 18 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={summary.months}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
            <XAxis dataKey="month" fontSize={11} stroke="var(--muted)" />
            <YAxis fontSize={11} stroke="var(--muted)" />
            <Tooltip />
            <Area type="monotone" dataKey="revenue" stroke="var(--mint)" fill="var(--mint-soft)" strokeWidth={2} />
            <Area type="monotone" dataKey="expenses" stroke="var(--danger)" fill="rgba(214,67,63,.12)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div className="finance-grid">
        <div className="card schedule-card" style={{ height: 260 }}>
          <p className="schedule-note" style={{ marginBottom: 10 }}>Répartition des dépenses</p>
          <ResponsiveContainer width="100%" height="85%">
            <PieChart>
              <Pie data={categories} dataKey="amountPct" nameKey="category" innerRadius={50} outerRadius={80} paddingAngle={2}>
                {categories.map((c) => <Cell key={c.category} fill={CATEGORY_COLORS[c.category] || "#5f7377"} />)}
              </Pie>
              <Tooltip formatter={(value) => `${value}%`} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="finance-stack">
          <div className="stat-card">
            <p className="stat-label">Chiffre d'affaires du mois</p>
            <p className="stat-value">{thisMonth.revenue.toLocaleString()}</p>
          </div>
          <div className="stat-card">
            <p className="stat-label">Charges d'exploitation</p>
            <p className="stat-value">{thisMonth.expenses.toLocaleString()}</p>
          </div>
          <div className="stat-card">
            <p className="stat-label">Prévision de rentabilité (ROI)</p>
            <p className="stat-value">{summary.roiForecastPct != null ? `${summary.roiForecastPct}%` : "Non disponible"}</p>
          </div>
        </div>
      </div>

      <div className="card progress-card" style={{ marginBottom: 14 }}>
        <p className="schedule-note">Trésorerie disponible</p>
        <p style={{ margin: "6px 0 0", fontFamily: "'Space Grotesk',sans-serif", fontSize: 24 }}>{summary.cashOnHand.toLocaleString()}</p>
      </div>
      <div className="card progress-card warn" style={{ marginBottom: 22 }}>
        <p className="schedule-note">Montants à régler</p>
        <p style={{ margin: "6px 0 0", fontFamily: "'Space Grotesk',sans-serif", fontSize: 24, color: "var(--warning)" }}>
          {summary.pendingPayables.toLocaleString()}
        </p>
      </div>

      <div className="section-row">
        <h2>Transactions</h2>
        <div className="segmented">
          {["all", "in", "out"].map((t) => (
            <button key={t} className={typeFilter === t ? "active" : ""} onClick={() => setTypeFilter(t)}>
              {t === "all" ? "Tout" : t === "in" ? "Entrées" : "Sorties"}
            </button>
          ))}
        </div>
      </div>
      <div className="card schedule-card">
        <table className="data-table">
          <thead>
            <tr><th>ID</th><th>Date</th><th>Catégorie</th><th>Contrepartie</th><th>Montant</th></tr>
          </thead>
          <tbody>
            {transactions.results.map((row) => (
              <tr key={row.id}>
                <td>{row.id}</td>
                <td>{row.date}</td>
                <td>{CATEGORY_LABELS[row.category] || row.category}</td>
                <td>{row.counterparty || "—"}</td>
                <td className={`amount ${row.amount >= 0 ? "in" : "out"}`}>{row.amount.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {transactions.results.length === 0 && <p className="empty-state">Aucune transaction pour le moment.</p>}
        <div className="pagination">
          <button disabled={transactions.page <= 1} onClick={() => loadTransactions(transactions.page - 1)}>Précédent</button>
          <span>Page {transactions.page} / {totalPages}</span>
          <button disabled={transactions.page >= totalPages} onClick={() => loadTransactions(transactions.page + 1)}>Suivant</button>
        </div>
      </div>
    </div>
  );
}
