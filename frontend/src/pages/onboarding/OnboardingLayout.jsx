import { ChevronLeft } from "lucide-react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { OnboardingProvider } from "../../context/OnboardingContext";
import AnimatedBackground from "../../components/AnimatedBackground";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import { useAuth } from "../../context/AuthContext";
import "../../styles/house-protocol-theme-light.css";
import "../auth-pages.css";
import "./onboarding.css";

const STEPS = [
  { path: "/onboarding/protocol", label: "1. Bâtiments" },
  { path: "/onboarding/stock", label: "2. Stock" },
  { path: "/onboarding/employees", label: "3. Employés" },
];

export default function OnboardingLayout() {
  useDocumentTitle("Configuration de la ferme");
  const { pathname } = useLocation();
  const { user } = useAuth();
  // "+ Nouvelle bande" reuses this same route tree to add a house to an already-configured
  // farm (OnboardingProtocolPage's own `isAddingHouse`, same condition here) — that flow only
  // ever visits step 1, then returns straight to the dashboard; it never reaches Stock/Employés.
  // The shell used to show the full 3-step wizard chrome regardless (steps it will never reach)
  // plus "Retour à l'accueil" pointing an already-logged-in user at the marketing landing page
  // instead of back to their dashboard — actively misleading, not just visual noise (2026-08-27
  // bugfix, docs/deviations.md — confirmed live via a headless-browser session showing exactly
  // this before the fix, not assumed from reading the code).
  const isAddingHouse = user?.is_configured;

  return (
    <OnboardingProvider>
      <div className="app-shell onboarding-shell">
        <AnimatedBackground src="/welcome-bg.jpg" />
        <div className="onboarding-progress">
          {isAddingHouse ? (
            <Link to="/dashboard" className="auth-back-link onboarding-back-link">
              <ChevronLeft size={15} strokeWidth={2} /> Retour au tableau de bord
            </Link>
          ) : (
            <>
              <Link to="/" className="auth-back-link onboarding-back-link">
                <ChevronLeft size={15} strokeWidth={2} /> Retour à l'accueil
              </Link>
              {STEPS.map((step) => (
                <span key={step.path} className={`onboarding-step ${pathname === step.path ? "active" : ""}`}>
                  {step.label}
                </span>
              ))}
            </>
          )}
        </div>
        <div className="onboarding-content">
          <Outlet />
        </div>
      </div>
    </OnboardingProvider>
  );
}
