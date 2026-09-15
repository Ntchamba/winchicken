import { createContext, useContext, useState } from "react";

const OnboardingContext = createContext(null);

// Categories are now dynamic (5 defaults + any custom ones), so `schedules` is keyed by
// category id rather than a fixed set of slugs — starts empty, HouseProtocolForm treats a
// missing key as an empty category.
const EMPTY_STOCK = { feed: [], veterinary: [], equipment: [], bedding: [] };

// Shared wizard state so "Back" never loses what was typed on a previous step (cahier des charges 7.4).
export function OnboardingProvider({ children }) {
  const [houseHeader, setHouseHeader] = useState({ buildingName: "", chicksPlaced: "", growthCycle: 56, growthCycleUnit: "Day", batchName: "" });
  const [categories, setCategories] = useState(null);
  const [schedules, setSchedules] = useState({});
  const [warehouse, setWarehouse] = useState({ name: "Entrepôt principal", leadTime: 3, leadTimeUnit: "Days" });
  const [stockData, setStockData] = useState(EMPTY_STOCK);
  const [employees, setEmployees] = useState([]);

  return (
    <OnboardingContext.Provider
      value={{
        houseHeader, setHouseHeader,
        categories, setCategories,
        schedules, setSchedules,
        warehouse, setWarehouse,
        stockData, setStockData,
        employees, setEmployees,
      }}
    >
      {children}
    </OnboardingContext.Provider>
  );
}

export function useOnboarding() {
  return useContext(OnboardingContext);
}
