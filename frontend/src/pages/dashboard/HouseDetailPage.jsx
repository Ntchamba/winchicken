import { useEffect, useState } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Loader2 } from "lucide-react";
import { batchesApi } from "../../api/endpoints";
import "../../styles/house-protocol-theme-light.css";
import "../../styles/dashboard-theme.css";

// batch.status is the raw BatchStatus backend enum (ACTIVE/CLOSED) — displayed only
// through this French label map, never shown raw.
const BATCH_STATUS_LABELS = { ACTIVE: "En cours", CLOSED: "Clôturée" };

export default function HouseDetailPage() {
  const { houseCode } = useParams();
  const { houses } = useOutletContext();
  const navigate = useNavigate();
  const house = houses.find((h) => h.houseCode === houseCode);

  const [batch, setBatch] = useState(null);
  const [dailyLogs, setDailyLogs] = useState([]);
  const [weeklyKpi, setWeeklyKpi] = useState(null);
  const [closing, setClosing] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);

  useEffect(() => {
    batchesApi.list(houseCode).then(({ data }) => {
      const results = data.results || data;
      const active = results.find((b) => b.status === "ACTIVE") || results[0];
      setBatch(active || null);
      if (active) {
        batchesApi.dailyLogs(active.batch_code).then((res) => setDailyLogs(res.data.results || res.data));
        batchesApi.weeklyKpi(active.batch_code).then((res) => setWeeklyKpi(res.data));
      }
    });
  }, [houseCode]);

  const handleClose = async () => {
    if (!batch) return;
    setClosing(true);
    try {
      await batchesApi.close(batch.batch_code);
      setConfirmClose(false);
      navigate(0);
    } finally {
      setClosing(false);
    }
  };

  const growthData = dailyLogs
    .filter((log) => log.avg_sample_weight)
    .map((log) => ({ date: log.log_date, weightKg: log.avg_sample_weight }));

  return (
    <div className="page-wrap">
      <div className="breadcrumb">
        Tableau de bord / <strong>{house?.name || houseCode}</strong>
        {houses.length > 1 && (
          <select value={houseCode} onChange={(e) => navigate(`/dashboard/houses/${e.target.value}`)}>
            {houses.map((h) => (
              <option key={h.houseCode} value={h.houseCode}>{h.name}</option>
            ))}
          </select>
        )}
      </div>

      <div className="card house-card" style={{ marginBottom: 18 }}>
        <div className="section-heading">
          <div>
            <span className="house-chip">{batch ? BATCH_STATUS_LABELS[batch.status] || batch.status : "AUCUNE BANDE ACTIVE"}</span>
            <h1 style={{ margin: "7px 0 0", fontFamily: "'Space Grotesk',sans-serif", fontSize: 22 }}>{house?.name || houseCode}</h1>
            {batch && (
              <p className="schedule-note">
                {batch.name ? (
                  <>Bande {batch.name} <span style={{ opacity: .6 }}>({batch.batch_code})</span></>
                ) : (
                  <>Bande {batch.batch_code}</>
                )}
                {" "}· {batch.current_count} volailles · démarrée le {batch.start_date}
              </p>
            )}
          </div>
          <div style={{ display: "flex", gap: 10 }}>
            <button className="add-button" onClick={() => navigate(`/dashboard/houses/${houseCode}/protocol`)}>Modifier le protocole</button>
            {batch?.status === "ACTIVE" && (
              <button className="delete-button" style={{ width: "auto", padding: "0 16px" }} onClick={() => setConfirmClose(true)}>
                Clôturer la bande
              </button>
            )}
          </div>
        </div>
      </div>

      {confirmClose && (
        <div className="card schedule-card" style={{ marginBottom: 18, borderColor: "var(--danger)" }}>
          <p style={{ margin: "0 0 12px", fontSize: 14 }}>
            Clôturer cette bande est définitif et génère le rapport financier de clôture. Continuer ?
          </p>
          <div style={{ display: "flex", gap: 10 }}>
            <button className="save-button" onClick={handleClose} disabled={closing}>
              {closing ? <Loader2 size={16} className="spin" /> : "Confirmer la clôture"}
            </button>
            <button className="add-button" onClick={() => setConfirmClose(false)}>Annuler</button>
          </div>
        </div>
      )}

      {!batch && <p className="empty-state">Ce bâtiment n'a pas encore de bande.</p>}

      {batch && (
        <>
          <div className="section-row"><h2>Courbe de croissance</h2></div>
          <div className="card schedule-card" style={{ marginBottom: 18, height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={growthData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
                <XAxis dataKey="date" fontSize={11} stroke="var(--muted)" />
                <YAxis fontSize={11} stroke="var(--muted)" />
                <Tooltip />
                <Line type="monotone" dataKey="weightKg" stroke="var(--mint-fill)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {weeklyKpi && (
            <>
              <div className="section-row"><h2>Tendance de l'indice de consommation</h2></div>
              <div className="card schedule-card" style={{ marginBottom: 18, height: 240 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={weeklyKpi.weeks}>
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
                  <BarChart data={weeklyKpi.weeks}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
                    <XAxis dataKey="week" fontSize={11} stroke="var(--muted)" />
                    <YAxis fontSize={11} stroke="var(--muted)" />
                    <Tooltip />
                    <Bar dataKey="mortalityPct" radius={[4, 4, 0, 0]}>
                      {weeklyKpi.weeks.map((w, i) => (
                        <Cell key={i} fill={w.mortalityPct > 5 / (weeklyKpi.weeks.length || 1) ? "var(--danger)" : "var(--mint-fill)"} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
