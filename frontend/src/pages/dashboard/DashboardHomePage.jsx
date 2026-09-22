import { useCallback, useEffect, useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import HomeDashboard from "../../components/HomeDashboard";
import ProtocolEditModal from "../../components/ProtocolEditModal";
import { alertsApi, batchesApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import useDocumentTitle from "../../hooks/useDocumentTitle";

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
  useDocumentTitle("Tableau de bord");
  const { houses, refreshHouses } = useOutletContext();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [enrichedHouses, setEnrichedHouses] = useState([]);
  const [activeBatches, setActiveBatches] = useState([]);
  const [growthSeries, setGrowthSeries] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [editingHouseCode, setEditingHouseCode] = useState(null);

  const loadBatches = useCallback(() => {
    batchesApi.list().then(({ data }) => {
      const batches = data.results || data;
      const active = batches.filter((b) => b.status === "ACTIVE");
      const byHouse = Object.fromEntries(active.map((b) => [b.house_code, b]));
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
      setActiveBatches(
        active.map((b) => ({
          batchCode: b.batch_code,
          name: b.name,
          houseCode: b.house_code,
          houseName: houses.find((h) => h.houseCode === b.house_code)?.name || b.house_code,
        }))
      );
    });
  }, [houses]);

  const loadGrowthCurves = useCallback(() => {
    batchesApi.growthCurves().then(({ data }) => setGrowthSeries(data));
  }, []);

  useEffect(() => {
    loadBatches();
    loadGrowthCurves();
    alertsApi.list().then(({ data }) => {
      const results = (data.results || data).filter((a) => a.status !== "RESOLVED").slice(0, 6);
      setAlerts(results.map((a) => ({ id: a.id, severity: a.severity, ruleType: a.ruleType, message: a.message, triggeredAt: a.triggered_at })));
    });
  }, [loadBatches, loadGrowthCurves]);

  const handleNavigate = (path) => {
    if (path === "new-batch") navigate("/onboarding/protocol");
    else navigate(path);
  };

  return (
    <>
      <HomeDashboard
        farmName={user.farm_name}
        houses={enrichedHouses}
        alerts={alerts}
        activeBatchList={activeBatches}
        growthSeries={growthSeries}
        stats={{
          activeBatches: enrichedHouses.filter((h) => h.status === "active").length,
          totalBirds: enrichedHouses.reduce((sum, h) => sum + (h.count || 0), 0),
          openAlerts: alerts.length,
        }}
        onNavigate={handleNavigate}
        onModifyBatch={setEditingHouseCode}
        onDailyLogged={loadGrowthCurves}
      />
      <ProtocolEditModal
        houseCode={editingHouseCode}
        onClose={() => setEditingHouseCode(null)}
        onSaved={() => {
          loadGrowthCurves();
          loadBatches();
          refreshHouses();
        }}
      />
    </>
  );
}
