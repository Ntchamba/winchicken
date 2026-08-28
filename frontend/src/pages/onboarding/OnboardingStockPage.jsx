import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import StockParametersForm from "../../components/StockParametersForm";
import { stockApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import { useOnboarding } from "../../context/OnboardingContext";

let seedRowId = 3000;

// Flat StockItemSerializer list -> `{ [categoryId]: [row] }` for StockParametersForm.
function buildData(items, categories) {
  const map = Object.fromEntries(categories.map((c) => [c.id, []]));
  for (const item of items) {
    (map[item.category] ||= []).push({
      id: seedRowId++,
      itemCode: item.item_code,
      item: item.name,
      feedStage: item.feed_stage || "STARTER",
      coldChain: !!item.cold_chain_required,
      threshold: item.alert_threshold,
      unit: item.unit,
      price: item.unit_price,
      supplier: item.supplier ?? null,
    });
  }
  return map;
}

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
          data: buildData(itemRes.data.items, categories),
          suppliers: supRes.data.results || supRes.data,
        });
      });
  }, [user.farm]);

  const handleSave = async (payload) => {
    setSaving(true);
    try {
      setWarehouse({ name: payload.warehouseName, currency: payload.currency, leadTime: payload.leadTime, leadTimeUnit: payload.leadTimeUnit });
      await stockApi.putItems(user.farm, payload.items);
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
      saving={saving}
      onSave={handleSave}
      onBack={() => navigate("/onboarding/protocol")}
    />
  );
}
