import { useEffect, useRef } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import DashboardLayout from "../../components/DashboardLayout";
import { HousesProvider, useHousesContext } from "../../context/HousesContext";
import { useAuth } from "../../context/AuthContext";
import useSidebarNotifications from "../../hooks/useSidebarNotifications";

const ROLE_LABELS = {
  ADMIN: "Administrateur", SECONDARY_ADMIN: "Administrateur secondaire", FARM_MANAGER: "Gérant de ferme",
  FARMER: "Fermier", WORKER: "Ouvrier", TECHNICIAN: "Technicien", CASHIER: "Caissier",
};

export default function DashboardShell() {
  return (
    <HousesProvider>
      <DashboardShellContent />
    </HousesProvider>
  );
}

// Split from DashboardShell (2026-08-25) so it can sit inside HousesProvider and read
// useHousesContext() — the provider itself has to wrap this, not be inside it.
function DashboardShellContent() {
  const { user, logout } = useAuth();
  const { houses, loading: housesLoading, refetch } = useHousesContext();
  const location = useLocation();
  const navigate = useNavigate();

  const canSeeFinancePendingCount = ["ADMIN", "FARM_MANAGER"].includes(user.role);
  const { unreadCount, stockLowCount, financePendingCount, openCasesCount, refetch: refetchCounts } =
    useSidebarNotifications(canSeeFinancePendingCount);

  // Kept alongside the on-demand refetch (called directly by ProtocolEditModal via
  // useHousesContext, see HousesContext's docstring) as a belt-and-suspenders refresh on
  // navigation — cheap, and catches any change made through a path that doesn't call refetch
  // itself. refetchCounts (2026-08-26) rides the same trigger — one shared refresh mechanism
  // for the house list and the bell/badge counts, not two independent ones.
  //
  // Only on an actual change of route: both hooks already fetch when they mount, and firing here
  // on the first render too sent every sidebar request twice per page load (four times in dev,
  // where StrictMode doubles effects) — seen in live QA, 2026-09-25.
  const refreshedFor = useRef(location.pathname);
  useEffect(() => {
    if (refreshedFor.current === location.pathname) return;
    refreshedFor.current = location.pathname;
    refetch();
    refetchCounts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      activeHash={location.hash}
      canManageHouses={["ADMIN", "FARM_MANAGER"].includes(user.role)}
      canSeeSalaires={["ADMIN", "FARM_MANAGER"].includes(user.role)}
      canSeeEmployees={["ADMIN", "SECONDARY_ADMIN"].includes(user.role)}
      canSeeCashier={["ADMIN", "CASHIER"].includes(user.role)}
      canSeePurchaseOrders={["ADMIN", "FARM_MANAGER", "CASHIER"].includes(user.role)}
      canSeeAudit={user.role === "ADMIN"}
      unreadCount={unreadCount}
      stockLowCount={stockLowCount}
      financePendingCount={financePendingCount}
      openCasesCount={openCasesCount}
      onCountsChanged={refetchCounts}
      onNavigate={(path) => navigate(path)}
      onLogout={handleLogout}
    >
      <Outlet context={{ houses, housesLoading, refreshHouses: refetch }} />
    </DashboardLayout>
  );
}
