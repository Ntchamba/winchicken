import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import VentesSection from "../../components/finances/VentesSection";
import AchatsSection from "../../components/finances/AchatsSection";
import SalairesSection from "../../components/finances/SalairesSection";
import GlobaleSection from "../../components/finances/GlobaleSection";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import "../../styles/dashboard-theme.css";
import QuickLinksBar from "../../components/QuickLinksBar";

/**
 * Single-page "Finances" view (2026-08-27, Finances restructure Part A) — one route,
 * `/dashboard/finances`, four sections stacked vertically. Clicking a sidebar sub-item
 * (DashboardLayout.jsx's accordion) navigates to `/dashboard/finances#<section>`, which this
 * page turns into a smooth in-page scroll rather than a route change — the hash never causes a
 * remount (react-router treats it as the same route), satisfying the task's own requirement
 * that the URL "must not change route" when switching sections.
 *
 * All 4 sections mount once, together, and each fetches its own data independently — which
 * means an action in one section (Salaires' "Marquer comme payé" creates a LABOR Expense) can
 * make another already-fetched section (Achats' breakdown, Globale's totals) stale without a
 * full page reload, since a same-route hash change never remounts anything. `financesVersion` is
 * bumped by SalairesSection after such an action and passed down as a fetch-effect dependency to
 * the sections whose totals it can affect, forcing them to refetch.
 */
export default function FinancesPage() {
  useDocumentTitle("Finances");
  const location = useLocation();
  const { user } = useAuth();
  const canSeeSalaires = ["ADMIN", "FARM_MANAGER"].includes(user.role);
  const [financesVersion, setFinancesVersion] = useState(0);
  const bumpFinancesVersion = () => setFinancesVersion((v) => v + 1);

  useEffect(() => {
    if (!location.hash) return;
    const id = location.hash.slice(1);
    // Deferred one tick so the target section (Salaires in particular, gated on `user.role`) has
    // already rendered before we try to find it.
    const t = setTimeout(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 0);
    return () => clearTimeout(t);
  }, [location.hash]);

  return (
    <div className="page-wrap">
      <QuickLinksBar />
      <div className="breadcrumb">Tableau de bord / <strong>Finances</strong></div>

      <section id="ventes" style={{ marginBottom: 40, scrollMarginTop: 24 }}>
        <h1 className="finances-section-title">Ventes</h1>
        <VentesSection />
      </section>

      <section id="achats" style={{ marginBottom: 40, scrollMarginTop: 24 }}>
        <h1 className="finances-section-title">Achats</h1>
        <AchatsSection refreshKey={financesVersion} />
      </section>

      {canSeeSalaires && (
        <section id="salaires" style={{ marginBottom: 40, scrollMarginTop: 24 }}>
          <h1 className="finances-section-title">Salaires</h1>
          <SalairesSection onPaymentRecorded={bumpFinancesVersion} />
        </section>
      )}

      <section id="globale" style={{ marginBottom: 12, scrollMarginTop: 24 }}>
        <h1 className="finances-section-title">Globale</h1>
        <GlobaleSection refreshKey={financesVersion} />
      </section>
    </div>
  );
}
