import { useCallback, useEffect, useState } from "react";
import { Pencil } from "lucide-react";
import StockEvolutionChart from "../../components/StockEvolutionChart";
import StockLevelsSection from "../../components/StockLevelsSection";
import CompositionsSection from "../../components/CompositionsSection";
import SuppliersSection from "../../components/SuppliersSection";
import StockParametersModal from "../../components/StockParametersModal";
import { stockApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import QuickLinksBar from "../../components/QuickLinksBar";

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
  const [items, setItems] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [compositions, setCompositions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);

  const refresh = useCallback(() => {
    return Promise.all([
      stockApi.evolution(farmId),
      stockApi.items(farmId),
      stockApi.suppliers(farmId),
      stockApi.compositions(farmId),
    ]).then(([evoRes, itemsRes, supRes, compRes]) => {
      setEvolution(evoRes.data);
      setItems(itemsRes.data.items || []);
      setSuppliers(supRes.data.results || supRes.data);
      setCompositions(compRes.data.results || compRes.data);
      setLoading(false);
    });
  }, [farmId]);

  useEffect(() => { refresh(); }, [refresh]);

  return (
    <div className="page-wrap">
      <QuickLinksBar />
      <div className="brand-row">
        <div>
          <p className="eyebrow">WINCHICKEN</p>
          <p className="brand-subtitle">Stock</p>
        </div>
        {/* Plain .save-button (no padding override) = the app's "big primary action" scale,
            same as the onboarding "Suivant" and the enlarged weighing/mortality "Enregistrer"
            buttons. width:auto kept — it sits in the brand row, not a full-width bar. */}
        <button className="save-button" style={{ marginLeft: "auto", width: "auto" }} onClick={() => setModalOpen(true)}>
          <Pencil size={15} strokeWidth={2} />
          Mettre à jour le stock
        </button>
      </div>

      {loading ? (
        <p className="empty-state">Chargement…</p>
      ) : (
        <>
          <StockEvolutionChart series={evolution} />
          <StockLevelsSection items={items} compositions={compositions} onChanged={refresh} />
          <CompositionsSection farmId={farmId} items={items} onChanged={refresh} />
          <SuppliersSection suppliers={suppliers} farmId={farmId} onChanged={refresh} />
        </>
      )}

      <StockParametersModal
        open={modalOpen}
        farmId={farmId}
        compositions={compositions}
        onClose={() => setModalOpen(false)}
        onSaved={refresh}
      />
    </div>
  );
}
