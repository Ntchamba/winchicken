import { useEffect, useState } from "react";
import StockParametersForm from "../../components/StockParametersForm";
import { stockApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";

const CATEGORY_TO_TAB = { FEED: "feed", VETERINARY: "veterinary", EQUIPMENT: "equipment", BEDDING: "bedding" };

export default function StockPage() {
  const { user } = useAuth();
  const [initialData, setInitialData] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    stockApi.items(user.farm).then(({ data }) => {
      const tabbed = { feed: [], veterinary: [], equipment: [], bedding: [] };
      for (const item of data.items) {
        const tab = CATEGORY_TO_TAB[item.category];
        tabbed[tab].push({
          id: item.item_code,
          itemCode: item.item_code,
          item: item.name,
          detail: tab === "feed" ? item.feed_stage : tab === "veterinary" ? (item.cold_chain_required ? "Chaîne du froid : Oui" : "Chaîne du froid : Non") : "",
          threshold: item.alert_threshold,
          unit: item.unit,
          price: item.unit_price,
          currentQuantity: item.current_quantity,
        });
      }
      setInitialData(tabbed);
    });
  }, [user.farm]);

  const handleSave = async (payload) => {
    setSaving(true);
    try {
      await stockApi.putItems(user.farm, payload.items);
    } finally {
      setSaving(false);
    }
  };

  if (!initialData) return <div className="page-wrap"><p className="empty-state">Chargement…</p></div>;

  return <StockParametersForm initialData={initialData} mode="management" saving={saving} onSave={handleSave} />;
}
