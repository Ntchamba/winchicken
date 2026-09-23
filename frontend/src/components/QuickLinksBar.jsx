import { NavLink, useLocation } from "react-router-dom";
import {
  Bell, CalendarDays, Coins, LayoutGrid, ListChecks, Package, Warehouse,
} from "lucide-react";
import "./quick-links-bar.css";

// The sections users move between constantly. Kept in one list so every view offers the same
// set and nobody has to go back to the main menu to cross from Finances to Stock.
const LINKS = [
  { to: "/dashboard/overview", inIconNav: true, label: "Bilan global", Icon: LayoutGrid },
  { to: "/dashboard/finances", inIconNav: true, label: "Finances", Icon: Coins },
  { to: "/dashboard/stock", inIconNav: true, label: "Stock", Icon: Package },
  { to: "/dashboard/houses", inIconNav: true, label: "Bâtiments", Icon: Warehouse },
  { to: "/dashboard/calendar", inIconNav: true, label: "Calendrier", Icon: CalendarDays },
  { to: "/dashboard/my-tasks", label: "Tâches du jour", Icon: ListChecks },
  { to: "/dashboard/alerts", label: "Alertes", Icon: Bell },
];

// `inIconNav` links are already one tap away in the phone top bar (DashboardLayout's
// "Navigation principale"), so at ≤600px only the rest stay here — no duplicate row.
const linkClass = (inIconNav, extra = "") =>
  ["quick-link", extra, inIconNav ? "quick-link--in-icon-nav" : ""].filter(Boolean).join(" ");

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
      {LINKS.map(({ to, label, Icon, inIconNav }) => {
        const current = pathname === to || pathname.startsWith(`${to}/`);
        if (current) {
          return (
            <span className={linkClass(inIconNav, "quick-link--current")} key={to} aria-current="page">
              <Icon size={15} strokeWidth={2} />
              {label}
            </span>
          );
        }
        return (
          <NavLink className={linkClass(inIconNav)} to={to} key={to}>
            <Icon size={15} strokeWidth={2} />
            {label}
          </NavLink>
        );
      })}
    </nav>
  );
}
