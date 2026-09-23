import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

// One color per line when several batches are overlaid on the same chart — cycles if there
// are more active batches than colors (unlikely on a single farm, but never breaks).
const LINE_COLORS = ["#0b8f68", "#2f6fed", "#d97706", "#c026d3", "#0891b2", "#dc2626"];

// Reshapes `[{batchCode, batchName, points: [{dayOfCycle, weightKg, survivalPct}]}]` (the shape
// GET /api/batches/growth-curves/ returns) into one row per distinct dayOfCycle across all
// series, each batch's value under its own `${batchCode}_${field}` key — recharts needs a
// single merged dataset to draw multiple independent lines on one XAxis, since each batch's
// points don't share the same set of logged days.
function mergeByDay(series, field) {
  const days = new Set();
  for (const s of series) for (const p of s.points) days.add(p.dayOfCycle);
  return [...days].sort((a, b) => a - b).map((day) => {
    const row = { dayOfCycle: day };
    for (const s of series) {
      const point = s.points.find((p) => p.dayOfCycle === day);
      if (point && point[field] != null) row[`${s.batchCode}_${field}`] = point[field];
    }
    return row;
  });
}

const ALL_METRICS = ["weight", "survival"];

/**
 * Shared growth-curve charts (weight kg + survival %, both vs day-of-cycle) used by both the
 * farm-wide global view (one overlaid line per active batch) and the per-house view (a single
 * series, passed as a one-item array) — same component, a `scope` prop only changes the legend/
 * empty-state copy, never the data-fetching or chart logic (2026-08-25).
 *
 * @param {{batchCode: string, batchName: string, points: {dayOfCycle: number, weightKg: ?number, survivalPct: ?number}[]}[]} series
 * @param {"all"|"single"} [scope] - "single" hides the legend (redundant with one line) and
 *   adjusts the empty-state message; "all" (default) shows a legend labeled by batch name.
 * @param {("weight"|"survival")[]} [metrics] - Which curves to draw (both by default). The
 *   house "Pesée" page shows the weight curve alone, next to the weighing form.
 */
export default function GrowthCurves({ series = [], scope = "all", metrics = ALL_METRICS }) {
  if (series.length === 0) {
    return (
      <p className="empty-state">
        {scope === "single" ? "Aucune donnée de croissance pour cette bande pour le moment." : "Aucune bande active pour le moment."}
      </p>
    );
  }

  const weightData = mergeByDay(series, "weightKg");
  const survivalData = mergeByDay(series, "survivalPct");
  // Weighing cadence is flexible (weekly/monthly, not necessarily daily, 2026-08-25) — a batch
  // can have DailyLog rows (mortality/eggs) with zero weight entries yet, which shouldn't render
  // as a blank/broken chart. `weightData` still gets built (mergeByDay omits null-weight days
  // rather than zeroing them), so this checks whether *any* day across *any* series actually has
  // a weight value before deciding whether to render the chart or the empty state.
  const hasAnyWeight = series.some((s) => s.points.some((p) => p.weightKg != null));

  return (
    <>
      {metrics.includes("weight") && <div className="section-row"><h2>Poids moyen (kg) — jour du cycle</h2></div>}
      {!metrics.includes("weight") ? null : hasAnyWeight ? (
        <div className="card schedule-card" style={{ marginBottom: 18, height: 260 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={weightData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
              <XAxis dataKey="dayOfCycle" fontSize={11} stroke="var(--muted)" label={{ value: "Jour du cycle", position: "insideBottom", offset: -4, fontSize: 11, fill: "var(--muted)" }} />
              <YAxis fontSize={11} stroke="var(--muted)" />
              <Tooltip />
              {scope === "all" && <Legend wrapperStyle={{ fontSize: 12 }} />}
              {series.map((s, i) => (
                <Line
                  key={s.batchCode}
                  type="monotone"
                  dataKey={`${s.batchCode}_weightKg`}
                  name={s.batchName || s.batchCode}
                  stroke={LINE_COLORS[i % LINE_COLORS.length]}
                  strokeWidth={2}
                  dot
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="empty-state" style={{ marginBottom: 18 }}>
          {scope === "single" ? "Aucune pesée enregistrée pour cette bande." : "Aucune pesée enregistrée pour les bandes actives."}
        </p>
      )}

      {metrics.includes("survival") && <div className="section-row"><h2>Survie (%) — jour du cycle</h2></div>}
      {metrics.includes("survival") && <div className="card schedule-card" style={{ marginBottom: 18, height: 260 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={survivalData}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
            <XAxis dataKey="dayOfCycle" fontSize={11} stroke="var(--muted)" label={{ value: "Jour du cycle", position: "insideBottom", offset: -4, fontSize: 11, fill: "var(--muted)" }} />
            <YAxis fontSize={11} stroke="var(--muted)" domain={[0, 100]} />
            <Tooltip />
            {scope === "all" && <Legend wrapperStyle={{ fontSize: 12 }} />}
            {series.map((s, i) => (
              <Line
                key={s.batchCode}
                type="monotone"
                dataKey={`${s.batchCode}_survivalPct`}
                name={s.batchName || s.batchCode}
                stroke={LINE_COLORS[i % LINE_COLORS.length]}
                strokeWidth={2}
                dot
                connectNulls
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>}
    </>
  );
}
