import { useEffect, useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import GrowthCurves from "../../components/GrowthCurves";
import WeeklyKpiCharts from "../../components/WeeklyKpiCharts";
import { batchesApi } from "../../api/endpoints";
import useDocumentTitle from "../../hooks/useDocumentTitle";

/**
 * "Évolution" destination of the house hub: the batch's growth and survival curves across
 * its cycle, then the weekly feed-conversion trend and weekly mortality. Moved here as-is
 * from the house page — same components, same two requests.
 */
export default function HouseEvolutionPage() {
  const { houseCode } = useParams();
  const { house, batch } = useOutletContext();
  useDocumentTitle(`Évolution — ${house?.name || "Bâtiment sans nom"}`);
  const batchCode = batch?.batch_code;

  // Each stored with what it was loaded for, so another house/batch never shows stale curves.
  const [growth, setGrowth] = useState(null);
  const [weeklyKpi, setWeeklyKpi] = useState(null);

  useEffect(() => {
    batchesApi.growthCurves({ house_code: houseCode }).then(({ data }) => setGrowth({ houseCode, data }));
  }, [houseCode]);

  useEffect(() => {
    if (batchCode) batchesApi.weeklyKpi(batchCode).then(({ data }) => setWeeklyKpi({ batchCode, data }));
  }, [batchCode]);

  const growthSeries = growth && growth.houseCode === houseCode ? growth.data : null;
  const currentWeeklyKpi = weeklyKpi && weeklyKpi.batchCode === batchCode ? weeklyKpi.data : null;

  return (
    <>
      <div className="section-row"><h1 className="house-section-title">Évolution</h1></div>
      {batch === null && <p className="empty-state">Ce bâtiment n'a pas encore de bande.</p>}
      {batch && (
        <>
          {growthSeries ? <GrowthCurves series={growthSeries} scope="single" /> : <p className="empty-state">Chargement des courbes…</p>}
          {currentWeeklyKpi && <WeeklyKpiCharts weeklyKpi={currentWeeklyKpi} />}
        </>
      )}
    </>
  );
}
