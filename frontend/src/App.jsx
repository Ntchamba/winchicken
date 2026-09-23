import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import ProtectedRoute from "./routes/ProtectedRoute";

import LandingPage from "./pages/LandingPage";
import CreateFarmPage from "./pages/CreateFarmPage";
import LoginPage from "./pages/LoginPage";
import DemoPage from "./demo/DemoPage";

import OnboardingLayout from "./pages/onboarding/OnboardingLayout";
import OnboardingProtocolPage from "./pages/onboarding/OnboardingProtocolPage";
import OnboardingStockPage from "./pages/onboarding/OnboardingStockPage";
import OnboardingEmployeesPage from "./pages/onboarding/OnboardingEmployeesPage";

import DashboardShell from "./pages/dashboard/DashboardShell";
import GlobalOverviewPage from "./pages/dashboard/GlobalOverviewPage";
import DashboardHomePage from "./pages/dashboard/DashboardHomePage";
import HousesListPage from "./pages/dashboard/HousesListPage";
import HouseDetailPage from "./pages/dashboard/HouseDetailPage";
import HouseLayout from "./pages/dashboard/HouseLayout";
import HouseCasesPage from "./pages/dashboard/HouseCasesPage";
import HouseEvolutionPage from "./pages/dashboard/HouseEvolutionPage";
import HouseTasksPage from "./pages/dashboard/HouseTasksPage";
import HouseWeighingPage from "./pages/dashboard/HouseWeighingPage";
import HouseProtocolPage from "./pages/dashboard/HouseProtocolPage";
import FinancesPage from "./pages/dashboard/FinancesPage";
import FinancesLayout from "./pages/dashboard/FinancesLayout";
import FinanceDestinationPage from "./pages/dashboard/FinanceDestinationPage";
import { FINANCE_SECTIONS } from "./pages/dashboard/financeSections";
import StockPage from "./pages/dashboard/StockPage";
import PurchaseOrdersPage from "./pages/dashboard/PurchaseOrdersPage";
import EmployeesPage from "./pages/dashboard/EmployeesPage";
import CashierPage from "./pages/dashboard/CashierPage";
import AlertsListPage from "./pages/dashboard/AlertsListPage";
import CalendarPage from "./pages/dashboard/CalendarPage";
import SettingsPage from "./pages/dashboard/SettingsPage";
import MyTasksPage from "./pages/dashboard/MyTasksPage";
import AuditLogPage from "./pages/dashboard/AuditLogPage";

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/create-farm" element={<CreateFarmPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/demo" element={<DemoPage />} />

        <Route element={<ProtectedRoute allowUnconfigured />}>
          <Route path="/onboarding" element={<OnboardingLayout />}>
            <Route path="protocol" element={<OnboardingProtocolPage />} />
            <Route path="stock" element={<OnboardingStockPage />} />
            <Route path="employees" element={<OnboardingEmployeesPage />} />
          </Route>
        </Route>

        <Route element={<ProtectedRoute />}>
          <Route path="/dashboard" element={<DashboardShell />}>
            <Route index element={<DashboardHomePage />} />
            <Route path="overview" element={<GlobalOverviewPage />} />
            <Route path="houses" element={<HousesListPage />} />
            <Route path="houses/:houseCode" element={<HouseLayout />}>
              <Route index element={<HouseDetailPage />} />
              <Route path="cases" element={<HouseCasesPage />} />
              <Route path="evolution" element={<HouseEvolutionPage />} />
              <Route path="tasks" element={<HouseTasksPage />} />
              <Route path="weighing" element={<HouseWeighingPage />} />
            </Route>
            <Route path="houses/:houseCode/protocol" element={<HouseProtocolPage />} />
            <Route path="finances" element={<FinancesLayout />}>
              <Route index element={<FinancesPage />} />
              {FINANCE_SECTIONS.map((section) => (
                <Route key={section.key} path={section.path} element={<FinanceDestinationPage section={section} />} />
              ))}
            </Route>
            <Route path="stock" element={<StockPage />} />
            <Route path="purchase-orders" element={<PurchaseOrdersPage />} />
            <Route path="employees" element={<EmployeesPage />} />
            <Route path="cashier" element={<CashierPage />} />
            <Route path="alerts" element={<AlertsListPage />} />
            <Route path="calendar" element={<CalendarPage />} />
            <Route path="my-tasks" element={<MyTasksPage />} />
            <Route path="audit" element={<AuditLogPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
