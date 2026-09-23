import { Navigate, useLocation, useOutletContext } from "react-router-dom";
import HubPage from "../../components/HubPage";
import GlobaleSection from "../../components/finances/GlobaleSection";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import { FINANCES_BASE, FINANCE_SECTIONS, visibleFinanceSections } from "./financeSections";
import "../../styles/dashboard-theme.css";

/**
 * Finances hub (2026-09-23): the index route of FinancesLayout. Globale — the farm-wide
 * summary — is the landing content, under a HubPage tree whose branches are the destinations
 * in FINANCE_SECTIONS (Ventes, Achats, Salaires), each its own route.
 *
 * Until then this was one page with four stacked sections reached by `#hash` (2026-08-27,
 * Finances restructure Part A), which is why a `financesVersion` counter used to be threaded
 * through: Salaires' "Marquer comme payé" left the already-mounted Achats and Globale stale.
 * Each destination now mounts when it is opened and fetches then, so the counter is gone.
 * An old `#ventes`-style link or bookmark is redirected to its route.
 */
export default function FinancesPage() {
  useDocumentTitle("Finances");
  const { hash } = useLocation();
  const { canSeeSalaires } = useOutletContext();

  const legacy = FINANCE_SECTIONS.find(({ key }) => hash === `#${key}`);
  if (legacy) return <Navigate to={`${FINANCES_BASE}/${legacy.path}`} replace />;

  const sections = visibleFinanceSections(canSeeSalaires).map(({ key, path, label, Icon, message }) => ({
    key, title: label, Icon, to: `${FINANCES_BASE}/${path}`, message,
  }));

  return (
    <>
      <h1 className="finances-section-title">Finances</h1>
      <HubPage ariaLabel="Sections des finances" core={{ label: "Vue globale" }} sections={sections} />

      <section id="globale" style={{ marginBottom: 12 }}>
        <h2 className="finances-section-title">Globale</h2>
        <GlobaleSection />
      </section>
    </>
  );
}
