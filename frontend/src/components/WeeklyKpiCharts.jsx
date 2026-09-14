import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

/**
 * FCR trend + weekly mortality charts — extracted from `HouseDetailPage` (2026-08-25) as their
 * own presentational piece. Unrelated to the day-of-cycle `GrowthCurves` component (this one is
 * week-indexed, from `GET /api/batches/{batchCode}/kpi/weekly/`).
 *
 * @param {{weeks: object[], referenceRange: {feedConversionRatio: number[], mortalityPct: number[]}}} weeklyKpi
 */
export default function WeeklyKpiCharts({ weeklyKpi }) {
  const weeks = weeklyKpi.weeks;

  return (
    <>
      <div className="section-row"><h2>Tendance de l'indice de consommation</h2></div>
      <div className="card schedule-card" style={{ marginBottom: 18, height: 240 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={weeks}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
            <XAxis dataKey="week" fontSize={11} stroke="var(--muted)" />
            <YAxis fontSize={11} stroke="var(--muted)" domain={[1.5, 2.8]} />
            <ReferenceArea y1={weeklyKpi.referenceRange.feedConversionRatio[0]} y2={weeklyKpi.referenceRange.feedConversionRatio[1]} fill="var(--mint-soft)" fillOpacity={0.5} />
            <Tooltip />
            <Line type="monotone" dataKey="feedConversionRatio" stroke="var(--mint)" strokeWidth={2} dot />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="section-row"><h2>Mortalité hebdomadaire</h2></div>
      <div className="card schedule-card" style={{ marginBottom: 18, height: 220 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={weeks}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
            <XAxis dataKey="week" fontSize={11} stroke="var(--muted)" />
            <YAxis fontSize={11} stroke="var(--muted)" />
            <Tooltip />
            <Bar dataKey="mortalityPct" radius={[4, 4, 0, 0]}>
              {weeks.map((w, i) => (
                <Cell key={i} fill={w.mortalityPct > 5 / (weeks.length || 1) ? "var(--danger)" : "var(--mint-fill)"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}
