import { useMemo, useState } from "react";
import {
  CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

const LINE_COLORS = ["#0b8f68", "#2f6fed", "#d97706", "#c026d3", "#0891b2", "#dc2626"];

// Merge every item's `points: [{date, quantity}]` into one row per distinct calendar date,
// each item's running quantity under its own `itemCode` key — recharts needs a single merged
// dataset to draw several independent lines on one XAxis (same approach as GrowthCurves).
function mergeByDate(series) {
  const dates = new Set();
  for (const s of series) for (const p of s.points) dates.add(p.date);
  return [...dates].sort().map((date) => {
    const row = { date };
    for (const s of series) {
      const point = s.points.find((p) => p.date === date);
      if (point) row[s.itemCode] = point.quantity;
    }
    return row;
  });
}

/**
 * Stock evolution charts — current quantity over calendar date, from the running balance of
 * StockMovement (IN adds, OUT subtracts). Calendar date (not day-of-cycle): stock isn't
 * batch-scoped the way growth curves are. A selector picks one item (line + a horizontal
 * reference line at its alertThreshold, so a dip below is obvious) or "Tous les articles"
 * (one line per item, no reference line).
 *
 * @param {{itemCode, name, unit, alertThreshold, points: {date, quantity}[]}[]} series
 */
export default function StockEvolutionChart({ series = [] }) {
  const withData = useMemo(() => series.filter((s) => s.points.length > 0), [series]);
  const [selected, setSelected] = useState("__all__");

  if (withData.length === 0) {
    return (
      <div className="card schedule-card" style={{ marginBottom: 18 }}>
        <div className="section-row"><h2>Évolution du stock</h2></div>
        <p className="empty-state">Aucun mouvement de stock enregistré pour le moment.</p>
      </div>
    );
  }

  const single = selected !== "__all__" ? withData.find((s) => s.itemCode === selected) : null;
  const shown = single ? [single] : withData;
  const chartData = mergeByDate(shown);

  return (
    <div className="card schedule-card" style={{ marginBottom: 18 }}>
      <div className="section-row" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
        <h2>Évolution du stock — quantité par date</h2>
        <select value={selected} onChange={(e) => setSelected(e.target.value)} aria-label="Choisir un article">
          <option value="__all__">Tous les articles</option>
          {withData.map((s) => <option key={s.itemCode} value={s.itemCode}>{s.name}</option>)}
        </select>
      </div>

      <div style={{ height: 300 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
            <XAxis dataKey="date" fontSize={11} stroke="var(--muted)" />
            <YAxis fontSize={11} stroke="var(--muted)" label={{ value: single ? single.unit : "quantité", angle: -90, position: "insideLeft", fontSize: 11, fill: "var(--muted)" }} />
            <Tooltip />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {single && (
              <ReferenceLine
                y={single.alertThreshold}
                stroke="#dc2626"
                strokeDasharray="5 4"
                label={{ value: `Seuil d'alerte (${single.alertThreshold})`, fontSize: 11, fill: "#dc2626", position: "insideTopRight" }}
              />
            )}
            {shown.map((s, i) => (
              <Line
                key={s.itemCode}
                type="stepAfter"
                dataKey={s.itemCode}
                name={s.name}
                stroke={LINE_COLORS[i % LINE_COLORS.length]}
                strokeWidth={2}
                dot
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
