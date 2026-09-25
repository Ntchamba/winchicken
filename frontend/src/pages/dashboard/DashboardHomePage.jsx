import { useCallback, useEffect, useState } from "react";
import { useNavigate, useOutletContext } from "react-router-dom";
import HomeDashboard from "../../components/HomeDashboard";
import ProtocolEditModal from "../../components/ProtocolEditModal";
import { alertsApi, batchesApi } from "../../api/endpoints";
import { fetchAllPages } from "../../api/pagination";
import { countOf } from "../../api/incidents";
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
  // Until the batches are in, the dashboard says "Chargement…" rather than "Aucune bande active".
  const [batchesLoaded, setBatchesLoaded] = useState(false);
  const [alertsLoaded, setAlertsLoaded] = useState(false);
  const [growthSeries, setGrowthSeries] = useState([]);
  const [alerts, setAlerts] = useState([]);
  // The card lists the 6 newest open alerts but counts all of them: it used to count the 6 it
  // showed, next to a health badge saying "46 alertes ouvertes" (live QA, 2026-09-25).
  const [openAlertCount, setOpenAlertCount] = useState(0);
  const [editingHouseCode, setEditingHouseCode] = useState(null);

  const loadBatches = useCallback(() => {
    // Every page, like useHouses: a farm with more than 20 active batches lost the rest here.
    fetchAllPages(batchesApi.listActive).then((batches) => {
      const active = batches.filter((b) => b.status === "ACTIVE");
      setEnrichedHouses(enrichHouses(houses, batches));
      setBatchesLoaded(true);
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
    alertsApi.listOpen().then(({ data }) => {
      setOpenAlertCount(countOf(data));
      setAlertsLoaded(true);
      const results = (data.results || data).slice(0, 6);
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
          openAlerts: openAlertCount,
        }}
        onNavigate={handleNavigate}
        onModifyBatch={setEditingHouseCode}
        onDailyLogged={loadGrowthCurves}
        loading={!batchesLoaded}
        alertsLoading={!alertsLoaded}
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
