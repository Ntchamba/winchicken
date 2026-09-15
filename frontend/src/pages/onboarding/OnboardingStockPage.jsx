import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import StockParametersForm from "../../components/StockParametersForm";
import { stockApi } from "../../api/endpoints";
import { saveStockItemsWithQuantities } from "../../api/stockSave";
import { buildStockRows } from "../../utils/stockRows";
import { useAuth } from "../../context/AuthContext";
import { useOnboarding } from "../../context/OnboardingContext";

export default function OnboardingStockPage() {
  const { warehouse, setWarehouse } = useOnboarding();
  const { user } = useAuth();
  const [saving, setSaving] = useState(false);
  const [state, setState] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    // The farm (and its four seeded stock categories) already exists by onboarding step 2.
    Promise.all([stockApi.categories(user.farm), stockApi.items(user.farm), stockApi.suppliers(user.farm)])
      .then(([catRes, itemRes, supRes]) => {
        const categories = catRes.data.results || catRes.data;
        setState({
          categories,
          data: buildStockRows(itemRes.data.items, categories),
          suppliers: supRes.data.results || supRes.data,
        });
      });
  }, [user.farm]);

  const handleSave = async (payload) => {
    setSaving(true);
    try {
      setWarehouse({ name: payload.warehouseName, leadTime: payload.leadTime, leadTimeUnit: payload.leadTimeUnit });
      // The Quantité column is the farm's opening stock. It only becomes a real stock level
      // once it is recorded as an IN movement — putItems alone dropped it, so a farm finished
      // onboarding reading 0 of everything it had just declared.
      await saveStockItemsWithQuantities(user.farm, payload.items, {
        note: "Stock d'ouverture (configuration initiale)",
      });
      navigate("/onboarding/employees");
    } finally {
      setSaving(false);
    }
  };

  if (!state) return <div className="page-wrap"><p className="empty-state">Chargement…</p></div>;

  return (
    <StockParametersForm
      warehouse={warehouse}
      initialData={state.data}
      initialCategories={state.categories}
      initialSuppliers={state.suppliers}
      farmId={user.farm}
      mode="onboarding"
      // A farm being set up almost always already has feed and vaccines in the barn. Without
      // this the Quantité column existed only in "Mettre à jour le stock", so a farm finished
      // onboarding reading 0 of everything and had to re-declare its opening stock elsewhere.
      showStockEntry
      saving={saving}
      onSave={handleSave}
      onBack={() => navigate("/onboarding/protocol")}
    />
  );
}
