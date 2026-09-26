import { useCallback, useEffect, useState } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import GrowthCurves from "../../components/GrowthCurves";
import WeighingSection from "../../components/WeighingSection";
import { batchesApi } from "../../api/endpoints";
import useDocumentTitle from "../../hooks/useDocumentTitle";

/**
 * "Pesée" destination of the house hub: the weighing form and the weight curve it feeds, on
 * one page, so a saved weighing shows up on the curve right under it. Weight entry lives only
 * here now — the global dashboard links to each house's Pesée instead of carrying its own
 * multi-batch copy (see HomeDashboard).
 */
export default function HouseWeighingPage() {
  const { houseCode } = useParams();
  const { house, batch } = useOutletContext();
  useDocumentTitle(`Pesée — ${house?.name || "Bâtiment sans nom"}`);

  // Stored with the house it was loaded for, so another house never shows a stale curve.
  const [growth, setGrowth] = useState(null);
  const loadGrowthCurve = useCallback(() => {
    batchesApi.growthCurves({ house_code: houseCode }).then(({ data }) => setGrowth({ houseCode, data }));
  }, [houseCode]);

  useEffect(() => {
    loadGrowthCurve();
  }, [loadGrowthCurve]);

  const growthSeries = growth && growth.houseCode === houseCode ? growth.data : null;

  return (
    <>
      <div className="section-row"><h1 className="house-section-title">Pesée</h1></div>
      {batch === null && <p className="empty-state">Ce bâtiment n'a pas encore de bande.</p>}
      {batch && (
        <>
          <WeighingSection batches={[{ batchCode: batch.batch_code, name: batch.name }]} onLogged={loadGrowthCurve} />
          {growthSeries
            ? <GrowthCurves series={growthSeries} scope="single" metrics={["weight"]} />
            : <p className="empty-state">Chargement de la courbe…</p>}
        </>
      )}
    </>
  );
}
