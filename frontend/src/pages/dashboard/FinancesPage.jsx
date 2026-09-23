import { useEffect, useState } from "react";
import { useLocation, useOutletContext } from "react-router-dom";
import HubPage from "../../components/HubPage";
import AchatsSection from "../../components/finances/AchatsSection";
import SalairesSection from "../../components/finances/SalairesSection";
import GlobaleSection from "../../components/finances/GlobaleSection";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import { FINANCES_BASE, visibleFinanceSections } from "./financeSections";
import "../../styles/dashboard-theme.css";

/**
 * Finances hub (2026-09-23): the index route of FinancesLayout. Globale — the farm-wide
 * summary — is the landing content, under a HubPage tree whose branches are the destinations
 * in FINANCE_SECTIONS, each its own route. Sections not yet moved to a route stay stacked
 * below, still reachable by `#hash` from the sidebar.
 *
 * History: single-page "Finances" view (2026-08-27, Finances restructure Part A) — one route,
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
  const { canSeeSalaires } = useOutletContext();
  const sections = visibleFinanceSections(canSeeSalaires).map(({ key, path, label, Icon, message }) => ({
    key, title: label, Icon, to: `${FINANCES_BASE}/${path}`, message,
  }));
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
    <>
      <h1 className="finances-section-title">Finances</h1>
      {sections.length > 0 && (
        <HubPage ariaLabel="Sections des finances" core={{ label: "Vue globale" }} sections={sections} />
      )}

      <section id="globale" style={{ marginBottom: 40, scrollMarginTop: 24 }}>
        <h2 className="finances-section-title">Globale</h2>
        <GlobaleSection refreshKey={financesVersion} />
      </section>

      <section id="achats" style={{ marginBottom: 40, scrollMarginTop: 24 }}>
        <h2 className="finances-section-title">Achats</h2>
        <AchatsSection refreshKey={financesVersion} />
      </section>

      {canSeeSalaires && (
        <section id="salaires" style={{ marginBottom: 40, scrollMarginTop: 24 }}>
          <h2 className="finances-section-title">Salaires</h2>
          <SalairesSection onPaymentRecorded={bumpFinancesVersion} />
        </section>
      )}
    </>
  );
}
