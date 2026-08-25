import { useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import DashboardLayout from "../../components/DashboardLayout";
import { batchesApi, housesApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";

const ROLE_LABELS = {
  ADMIN: "Administrateur", SECONDARY_ADMIN: "Administrateur secondaire", FARM_MANAGER: "Gérant de ferme",
  FARMER: "Fermier", WORKER: "Ouvrier", TECHNICIAN: "Technicien", CASHIER: "Caissier",
};

// PoultryHouse has no productionType of its own (only PoultryBatch does) — the sidebar's
// Egg-vs-Bird icon is derived from each house's active batch, defaulting to Broiler for a
// house with no active batch yet (a house-code lookup, not an assumption about the farm).
const TYPE_LABELS = { BROILER: "Broiler", PULLET: "Pullet", LAYER: "Layer" };

export default function DashboardShell() {
  const { user, logout } = useAuth();
  const [houses, setHouses] = useState([]);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    Promise.all([housesApi.list(), batchesApi.list()]).then(([housesRes, batchesRes]) => {
      const houseResults = housesRes.data.results || housesRes.data;
      const batchResults = batchesRes.data.results || batchesRes.data;
      const activeTypeByHouse = Object.fromEntries(
        batchResults.filter((b) => b.status === "ACTIVE").map((b) => [b.house_code, b.production_type])
      );
      setHouses(
        houseResults.map((h) => ({
          houseCode: h.house_code,
          name: h.name,
          type: TYPE_LABELS[activeTypeByHouse[h.house_code]] || "Broiler",
        }))
      );
    });
  }, [location.pathname]);

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  return (
    <DashboardLayout
      houses={houses}
      user={{ name: user.name, role: ROLE_LABELS[user.role] || user.role }}
      activePath={location.pathname}
      canManageHouses={["ADMIN", "FARM_MANAGER"].includes(user.role)}
      canSeeEmployees={["ADMIN", "SECONDARY_ADMIN"].includes(user.role)}
      canSeeCashier={["ADMIN", "CASHIER"].includes(user.role)}
      onNavigate={(path) => navigate(path)}
      onLogout={handleLogout}
    >
      <Outlet context={{ houses }} />
    </DashboardLayout>
  );
}
