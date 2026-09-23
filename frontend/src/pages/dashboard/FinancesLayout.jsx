import { Link, Outlet, useLocation } from "react-router-dom";
import QuickLinksBar from "../../components/QuickLinksBar";
import { useAuth } from "../../context/AuthContext";
import { FINANCES_BASE, FINANCE_SECTIONS, financeCrossLinks } from "./financeSections";
import "../../styles/dashboard-theme.css";
import "./house-hub.css";

/**
 * Parent route of `/dashboard/finances` (the Globale hub) and its destinations. Owns the
 * breadcrumb and the cross-links so every destination is reachable from every other one, and
 * works out once whether this role may see Salaires.
 */
export default function FinancesLayout() {
  const { pathname } = useLocation();
  const { user } = useAuth();
  const canSeeSalaires = ["ADMIN", "FARM_MANAGER"].includes(user.role);
  const section = FINANCE_SECTIONS.find(({ path }) => pathname === `${FINANCES_BASE}/${path}`);

  return (
    <div className="page-wrap">
      <QuickLinksBar sections={financeCrossLinks(canSeeSalaires)} sectionsLabel="Sections des finances" />
      <div className="breadcrumb">
        Tableau de bord /{" "}
        {section ? (
          <>
            <Link to={FINANCES_BASE}>Finances</Link> / <strong>{section.label}</strong>
          </>
        ) : (
          <strong>Finances</strong>
        )}
      </div>
      <Outlet context={{ canSeeSalaires }} />
    </div>
  );
}
