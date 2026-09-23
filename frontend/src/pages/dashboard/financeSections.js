import { Banknote, LayoutGrid, ShoppingCart, TrendingUp } from "lucide-react";
import VentesSection from "../../components/finances/VentesSection";
import AchatsSection from "../../components/finances/AchatsSection";
import SalairesSection from "../../components/finances/SalairesSection";

export const FINANCES_BASE = "/dashboard/finances";

/**
 * Finances destinations, in display order. One list feeds the hub's branches (FinancesPage),
 * the cross-links row (FinancesLayout -> QuickLinksBar) and the routes' titles, so none of
 * them can offer a different set. `restricted` entries are shown only to roles that may see
 * them (Salaires: Admin / Farm Manager, enforced server-side too).
 */
export const FINANCE_SECTIONS = [
  { key: "ventes", path: "ventes", label: "Ventes", Icon: TrendingUp, message: "Chiffre d'affaires par période", Component: VentesSection },
  { key: "achats", path: "achats", label: "Achats", Icon: ShoppingCart, message: "Achats et charges par période", Component: AchatsSection },
  {
    key: "salaires", path: "salaires", label: "Salaires", Icon: Banknote, message: "Paie des employés",
    Component: SalairesSection, restricted: true,
  },
];

export const visibleFinanceSections = (canSeeSalaires) =>
  FINANCE_SECTIONS.filter((section) => !section.restricted || canSeeSalaires);

/** Cross-links row: the hub (Globale) first, then every destination the role can open. */
export function financeCrossLinks(canSeeSalaires) {
  return [
    { to: FINANCES_BASE, label: "Globale", Icon: LayoutGrid },
    ...visibleFinanceSections(canSeeSalaires).map(({ path, label, Icon }) => ({ to: `${FINANCES_BASE}/${path}`, label, Icon })),
  ];
}
