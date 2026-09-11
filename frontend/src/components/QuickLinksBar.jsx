import { NavLink, useLocation } from "react-router-dom";
import {
  Bell, CalendarDays, Coins, LayoutGrid, ListChecks, Package, Warehouse,
} from "lucide-react";
import "./quick-links-bar.css";

// The sections users move between constantly. Kept in one list so every view offers the same
// set and nobody has to go back to the main menu to cross from Finances to Stock.
const LINKS = [
  { to: "/dashboard/overview", label: "Bilan global", Icon: LayoutGrid },
  { to: "/dashboard/finances", label: "Finances", Icon: Coins },
  { to: "/dashboard/stock", label: "Stock", Icon: Package },
  { to: "/dashboard/houses", label: "Bâtiments", Icon: Warehouse },
  { to: "/dashboard/calendar", label: "Calendrier", Icon: CalendarDays },
  { to: "/dashboard/my-tasks", label: "Tâches du jour", Icon: ListChecks },
  { to: "/dashboard/alerts", label: "Alertes", Icon: Bell },
];

/**
 * Horizontal shortcuts between the main sections, shown at the top of each of them.
 *
 * The link matching the current page is rendered as plain text rather than a link — a
 * shortcut to the page you are already on is noise, and removing it keeps the row shorter
 * where it matters most (phone width, where the row scrolls sideways).
 */
export default function QuickLinksBar() {
  const { pathname } = useLocation();

  return (
    <nav className="quick-links" aria-label="Accès rapide">
      {LINKS.map(({ to, label, Icon }) => {
        const current = pathname === to || pathname.startsWith(`${to}/`);
        if (current) {
          return (
            <span className="quick-link quick-link--current" key={to} aria-current="page">
              <Icon size={15} strokeWidth={2} />
              {label}
            </span>
          );
        }
        return (
          <NavLink className="quick-link" to={to} key={to}>
            <Icon size={15} strokeWidth={2} />
            {label}
          </NavLink>
        );
      })}
    </nav>
  );
}
