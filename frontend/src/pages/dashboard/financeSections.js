import { LayoutGrid } from "lucide-react";

export const FINANCES_BASE = "/dashboard/finances";

/**
 * Finances destinations, in display order. One list feeds the hub's branches (FinancesPage),
 * the cross-links row (FinancesLayout -> QuickLinksBar) and the routes' titles, so none of
 * them can offer a different set. `restricted` entries are shown only to roles that may see
 * them (Salaires: Admin / Farm Manager, enforced server-side too).
 */
export const FINANCE_SECTIONS = [];

export const visibleFinanceSections = (canSeeSalaires) =>
  FINANCE_SECTIONS.filter((section) => !section.restricted || canSeeSalaires);

/** Cross-links row: the hub (Globale) first, then every destination the role can open. */
export function financeCrossLinks(canSeeSalaires) {
  return [
    { to: FINANCES_BASE, label: "Globale", Icon: LayoutGrid },
    ...visibleFinanceSections(canSeeSalaires).map(({ path, label, Icon }) => ({ to: `${FINANCES_BASE}/${path}`, label, Icon })),
  ];
}
