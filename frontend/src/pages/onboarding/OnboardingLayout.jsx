import { ChevronLeft } from "lucide-react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { OnboardingProvider } from "../../context/OnboardingContext";
import AnimatedBackground from "../../components/AnimatedBackground";
import "../../styles/house-protocol-theme-light.css";
import "../auth-pages.css";
import "./onboarding.css";

const STEPS = [
  { path: "/onboarding/protocol", label: "1. Bâtiments" },
  { path: "/onboarding/stock", label: "2. Stock" },
  { path: "/onboarding/employees", label: "3. Employés" },
];

export default function OnboardingLayout() {
  const { pathname } = useLocation();

  return (
    <OnboardingProvider>
      <div className="app-shell onboarding-shell">
        <AnimatedBackground src="/welcome-bg.jpg" />
        <div className="onboarding-progress">
          <Link to="/" className="auth-back-link onboarding-back-link">
            <ChevronLeft size={15} strokeWidth={2} /> Retour à l'accueil
          </Link>
          {STEPS.map((step) => (
            <span key={step.path} className={`onboarding-step ${pathname === step.path ? "active" : ""}`}>
              {step.label}
            </span>
          ))}
        </div>
        <div className="onboarding-content">
          <Outlet />
        </div>
      </div>
    </OnboardingProvider>
  );
}
