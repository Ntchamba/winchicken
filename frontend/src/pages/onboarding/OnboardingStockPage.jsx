import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import StockParametersForm from "../../components/StockParametersForm";
import { stockApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import { useOnboarding } from "../../context/OnboardingContext";

const CATEGORY_TO_TAB = { FEED: "feed", VETERINARY: "veterinary", EQUIPMENT: "equipment", BEDDING: "bedding" };

const isStockEmpty = (data) => Object.values(data).every((rows) => rows.length === 0);

// Backend FeedStage enum values ("STARTER") don't match StockParametersForm's <select>
// option values ("Starter") — without this conversion the feed-stage dropdown fails to
// pre-select the item's actual stage when editing (see docs/deviations.md).
function feedStageToDetail(feedStage) {
  if (!feedStage || feedStage === "NOT_APPLICABLE") return "";
  return feedStage.charAt(0) + feedStage.slice(1).toLowerCase();
}

function tabifyItems(items) {
  const tabbed = { feed: [], veterinary: [], equipment: [], bedding: [] };
  for (const item of items) {
    const tab = CATEGORY_TO_TAB[item.category];
    tabbed[tab].push({
      id: item.item_code,
      itemCode: item.item_code,
      item: item.name,
      detail: tab === "feed" ? feedStageToDetail(item.feed_stage) : tab === "veterinary" ? (item.cold_chain_required ? "Chaîne du froid : Oui" : "Chaîne du froid : Non") : "",
      threshold: item.alert_threshold,
      unit: item.unit,
      price: item.unit_price,
    });
  }
  return tabbed;
}

export default function OnboardingStockPage() {
  const { warehouse, setWarehouse, stockData, setStockData } = useOnboarding();
  const { user } = useAuth();
  const [saving, setSaving] = useState(false);
  const navigate = useNavigate();

  // Reached directly (not through the wizard) on an already-configured farm — e.g. a
  // stale bookmark or browser back/forward. Load the real stock instead of starting
  // from the wizard's empty context, so saving here can never wipe existing items.
  useEffect(() => {
    if (user?.is_configured && isStockEmpty(stockData)) {
      stockApi.items(user.farm).then(({ data }) => setStockData(tabifyItems(data.items)));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.is_configured]);

  const handleSave = async (payload) => {
    setSaving(true);
    try {
      setWarehouse({ name: payload.warehouseName, currency: payload.currency, leadTime: payload.leadTime, leadTimeUnit: payload.leadTimeUnit });
      const { data } = await stockApi.putItems(user.farm, payload.items);
      const tabbed = { feed: [], veterinary: [], equipment: [], bedding: [] };
      for (const item of data.items) {
        const tab = CATEGORY_TO_TAB[item.category];
        tabbed[tab].push({
          id: item.item_code,
          itemCode: item.item_code,
          item: item.name,
          detail: tab === "feed" ? feedStageToDetail(item.feed_stage) : tab === "veterinary" ? (item.cold_chain_required ? "Chaîne du froid : Oui" : "Chaîne du froid : Non") : "",
          threshold: item.alert_threshold,
          unit: item.unit,
          price: item.unit_price,
        });
      }
      setStockData(tabbed);
      navigate("/onboarding/employees");
    } finally {
      setSaving(false);
    }
  };

  return (
    <StockParametersForm
      warehouse={warehouse}
      initialData={stockData}
      mode="onboarding"
      saving={saving}
      onSave={handleSave}
      onBack={() => navigate("/onboarding/protocol")}
    />
  );
}
