import { useState } from "react";
import { useNavigate } from "react-router-dom";
import HouseProtocolForm from "../../components/HouseProtocolForm";
import { onboardingApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import { useOnboarding } from "../../context/OnboardingContext";

export default function OnboardingProtocolPage() {
  const { houseHeader, setHouseHeader, categories, setCategories, schedules, setSchedules } = useOnboarding();
  const [saving, setSaving] = useState(false);
  const navigate = useNavigate();
  const { user, refreshMe } = useAuth();
  // Farm already configured (stock/employees already exist) -> this is the
  // "+ New house" flow, not first-time onboarding. Skip straight to the
  // dashboard instead of forcing the stock/employees steps again, which
  // would otherwise let the stock step's full-replace PUT wipe out the
  // farm's existing stock items.
  const isAddingHouse = user?.is_configured;

  const handleSave = async (payload) => {
    setSaving(true);
    try {
      setHouseHeader({ ...payload.house, batchName: payload.batchName });
      setCategories(payload.categories);
      const scheduleMap = {};
      for (const cat of payload.categories) scheduleMap[cat.id] = [];
      for (const line of payload.protocolLines) {
        const cat = payload.categories[line.categoryIndex];
        if (cat) scheduleMap[cat.id].push(line);
      }
      setSchedules(scheduleMap);

      await onboardingApi.submit({
        house: {
          name: payload.house.buildingName,
          maxCapacity: payload.house.chicksPlaced,
        },
        batch: {
          name: payload.batchName,
          productionType: "BROILER",
          initialCount: payload.house.chicksPlaced,
          startDate: new Date().toISOString().slice(0, 10),
          growthCycleValue: payload.house.growthCycle,
          growthCycleUnit: payload.house.growthCycleUnit.toUpperCase(),
        },
        // Only the categories beyond the 5 auto-seeded defaults need to be sent —
        // apps.houses.signals seeds those from apps.protocols.models.DEFAULT_PROTOCOL_CATEGORIES.
        customCategories: payload.categories.slice(5).map(({ label, icon }) => ({ label, icon })),
        protocolLines: payload.protocolLines,
      });
      if (isAddingHouse) {
        await refreshMe();
        navigate("/dashboard", { replace: true });
      } else {
        navigate("/onboarding/stock");
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <HouseProtocolForm
      initialHeader={houseHeader}
      initialCategories={categories}
      initialSchedules={schedules}
      mode="onboarding"
      saving={saving}
      onSave={handleSave}
    />
  );
}
