import { useEffect, useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import HomeDashboard from "../../components/HomeDashboard";
import { alertsApi, batchesApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";

function dayInCycle(batch) {
  const start = new Date(batch.start_date);
  const days = Math.floor((Date.now() - start.getTime()) / 86400000) + 1;
  return Math.max(1, days);
}

function cycleLength(batch) {
  if (!batch.planned_end_date) return null;
  const start = new Date(batch.start_date);
  const end = new Date(batch.planned_end_date);
  return Math.round((end.getTime() - start.getTime()) / 86400000);
}

export default function DashboardHomePage() {
  const { houses } = useOutletContext();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [enrichedHouses, setEnrichedHouses] = useState([]);
  const [alerts, setAlerts] = useState([]);

  useEffect(() => {
    let cancelled = false;
    batchesApi.list().then(({ data }) => {
      if (cancelled) return;
      const batches = data.results || data;
      const byHouse = Object.fromEntries(batches.filter((b) => b.status === "ACTIVE").map((b) => [b.house_code, b]));
      setEnrichedHouses(
        houses.map((house) => {
          const batch = byHouse[house.houseCode];
          if (!batch) return { ...house, status: "void", day: null, cycle: null, count: 0, capacity: 0 };
          return {
            ...house,
            status: "active",
            day: dayInCycle(batch),
            cycle: cycleLength(batch),
            count: batch.current_count,
            capacity: batch.current_count,
          };
        })
      );
    });
    alertsApi.list().then(({ data }) => {
      if (cancelled) return;
      const results = (data.results || data).filter((a) => a.status !== "RESOLVED").slice(0, 6);
      setAlerts(results.map((a) => ({ id: a.id, severity: a.severity, ruleType: a.ruleType, message: a.message, triggeredAt: a.triggered_at })));
    });
    return () => { cancelled = true; };
  }, [houses]);

  const handleNavigate = (path) => {
    if (path === "new-batch" || path === "protocol") navigate("/onboarding/protocol");
    else navigate(path);
  };

  return (
    <HomeDashboard
      farmName={user.farm_name}
      houses={enrichedHouses}
      alerts={alerts}
      stats={{
        activeBatches: enrichedHouses.filter((h) => h.status === "active").length,
        totalBirds: enrichedHouses.reduce((sum, h) => sum + (h.count || 0), 0),
        openAlerts: alerts.length,
      }}
      onNavigate={handleNavigate}
    />
  );
}
