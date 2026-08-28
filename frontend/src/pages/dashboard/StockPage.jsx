import { useCallback, useEffect, useState } from "react";
import { Pencil } from "lucide-react";
import StockEvolutionChart from "../../components/StockEvolutionChart";
import SuppliersSection from "../../components/SuppliersSection";
import StockParametersModal from "../../components/StockParametersModal";
import { stockApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import useDocumentTitle from "../../hooks/useDocumentTitle";

/**
 * /dashboard/stock — a batch-view-style dashboard: stock evolution charts + a "Fournisseurs"
 * section by default. The stock parameter form is no longer shown here; it opens in the
 * "Mettre à jour le stock" modal (same backdrop-blur pattern as the batch "Modifier" modal).
 * On save the modal closes and the charts/suppliers below refresh immediately.
 */
export default function StockPage() {
  useDocumentTitle("Stock");
  const { user } = useAuth();
  const farmId = user.farm;

  const [evolution, setEvolution] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);

  const refresh = useCallback(() => {
    return Promise.all([stockApi.evolution(farmId), stockApi.suppliers(farmId)]).then(
      ([evoRes, supRes]) => {
        setEvolution(evoRes.data);
        setSuppliers(supRes.data.results || supRes.data);
        setLoading(false);
      }
    );
  }, [farmId]);

  useEffect(() => { refresh(); }, [refresh]);

  return (
    <div className="page-wrap">
      <div className="brand-row">
        <div>
          <p className="eyebrow">WINCHICKEN</p>
          <p className="brand-subtitle">Stock</p>
        </div>
        <button className="save-button" style={{ marginLeft: "auto", width: "auto", padding: "0 18px" }} onClick={() => setModalOpen(true)}>
          <Pencil size={15} strokeWidth={2} />
          Mettre à jour le stock
        </button>
      </div>

      {loading ? (
        <p className="empty-state">Chargement…</p>
      ) : (
        <>
          <StockEvolutionChart series={evolution} />
          <SuppliersSection suppliers={suppliers} farmId={farmId} onChanged={refresh} />
        </>
      )}

      <StockParametersModal
        open={modalOpen}
        farmId={farmId}
        onClose={() => setModalOpen(false)}
        onSaved={refresh}
      />
    </div>
  );
}
