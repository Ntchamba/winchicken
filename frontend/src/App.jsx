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
import DashboardHomePage from "./pages/dashboard/DashboardHomePage";
import HousesListPage from "./pages/dashboard/HousesListPage";
import HouseDetailPage from "./pages/dashboard/HouseDetailPage";
import HouseProtocolPage from "./pages/dashboard/HouseProtocolPage";
import FinancePage from "./pages/dashboard/FinancePage";
import StockPage from "./pages/dashboard/StockPage";
import EmployeesPage from "./pages/dashboard/EmployeesPage";
import CashierPage from "./pages/dashboard/CashierPage";
import AlertsListPage from "./pages/dashboard/AlertsListPage";
import SettingsPage from "./pages/dashboard/SettingsPage";

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
            <Route path="houses" element={<HousesListPage />} />
            <Route path="houses/:houseCode" element={<HouseDetailPage />} />
            <Route path="houses/:houseCode/protocol" element={<HouseProtocolPage />} />
            <Route path="finance" element={<FinancePage />} />
            <Route path="stock" element={<StockPage />} />
            <Route path="employees" element={<EmployeesPage />} />
            <Route path="cashier" element={<CashierPage />} />
            <Route path="alerts" element={<AlertsListPage />} />
            <Route path="settings" element={<SettingsPage />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
