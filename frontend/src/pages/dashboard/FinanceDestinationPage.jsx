import { Navigate, useOutletContext } from "react-router-dom";
import useDocumentTitle from "../../hooks/useDocumentTitle";
import { FINANCES_BASE } from "./financeSections";

/**
 * One Finances destination (Ventes, Achats, Salaires) on its own route, under FinancesLayout.
 * Renders the section component unchanged — same data, same actions as when it was a block of
 * the single Finances page. A restricted section opened by a role that may not see it (a typed
 * or bookmarked URL) goes back to the hub rather than rendering an empty shell; the API
 * refuses the data either way.
 *
 * @param {{label: string, restricted?: boolean, Component: import("react").ComponentType}} section
 */
export default function FinanceDestinationPage({ section }) {
  const { canSeeSalaires } = useOutletContext();
  useDocumentTitle(`${section.label} — Finances`);
  if (section.restricted && !canSeeSalaires) return <Navigate to={FINANCES_BASE} replace />;

  const { Component } = section;
  return (
    <>
      <h1 className="finances-section-title">{section.label}</h1>
      <Component />
    </>
  );
}
