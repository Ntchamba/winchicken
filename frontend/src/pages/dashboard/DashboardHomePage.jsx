import { useCallback, useEffect, useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import HomeDashboard from "../../components/HomeDashboard";
import ProtocolEditModal from "../../components/ProtocolEditModal";
import { alertsApi, batchesApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import { enrichHouses } from "../../utils/dashboardHouses";

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
    batchesApi.listActive().then(({ data }) => {
      const batches = data.results || data;
      const active = batches.filter((b) => b.status === "ACTIVE");
      setEnrichedHouses(enrichHouses(houses, batches));
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
