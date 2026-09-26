import { NavLink, useLocation } from "react-router-dom";
import {
  Bell, CalendarDays, Coins, LayoutGrid, ListChecks, Package, Warehouse,
} from "lucide-react";
import "./quick-links-bar.css";

// The sections users move between constantly. Kept in one list so every view offers the same
// set and nobody has to go back to the main menu to cross from Finances to Stock.
//
// `inIconNav`: already one tap away in the phone top bar (DashboardLayout's icon row), so
// hidden here at <=600px — no duplicate row on a phone.
// `inSidebar`: already a permanent link in the desktop sidebar (DashboardLayout.jsx), so
// hidden here at >=901px (the width where that sidebar stops being a drawer and is always on
// screen) — same "no duplicate row" logic, applied to the other end of the width range.
// "Bâtiments" is deliberately NOT `inSidebar`: the sidebar lists individual houses, never an
// aggregate list, so this is the only link to /dashboard/houses at any width above 600px.
const LINKS = [
  { to: "/dashboard/overview", inIconNav: true, inSidebar: true, label: "Bilan global", Icon: LayoutGrid },
  { to: "/dashboard/finances", inIconNav: true, inSidebar: true, label: "Finances", Icon: Coins },
  { to: "/dashboard/stock", inIconNav: true, inSidebar: true, label: "Stock", Icon: Package },
  { to: "/dashboard/houses", inIconNav: true, label: "Bâtiments", Icon: Warehouse },
  { to: "/dashboard/calendar", inIconNav: true, inSidebar: true, label: "Calendrier", Icon: CalendarDays },
  { to: "/dashboard/my-tasks", inSidebar: true, label: "Mes tâches", Icon: ListChecks },
  { to: "/dashboard/alerts", label: "Alertes", Icon: Bell },
];

const linkClass = (inIconNav, inSidebar, extra = "") =>
  ["quick-link", extra, inIconNav ? "quick-link--in-icon-nav" : "", inSidebar ? "quick-link--in-sidebar" : ""]
    .filter(Boolean).join(" ");

/**
 * Horizontal shortcuts between the main sections, shown at the top of each of them.
 *
 * The link matching the current page is rendered as plain text rather than a link — a
 * shortcut to the page you are already on is noise, and removing it keeps the row shorter
 * where it matters most (phone width, where the row scrolls sideways).
 *
 * @param {{to: string, label: string, Icon: import("react").ComponentType}[]} [sections] -
 *   Destinations of the hub the page belongs to (a house's Cas signalés / Évolution / …),
 *   rendered as a second row above the global links. Matched exactly, so the hub's own entry
 *   is not "current" on every one of its destinations. The same list the hub builds its
 *   branches from, so the two can never offer different sets.
 * @param {string} [sectionsLabel] - aria-label for that row (French).
 */
export default function QuickLinksBar({ sections = [], sectionsLabel = "Sections" }) {
  const { pathname } = useLocation();

  return (
    <>
      {sections.length > 0 && (
        <nav className="quick-links quick-links--sections" aria-label={sectionsLabel}>
          {sections.map(({ to, label, Icon }) => (
            pathname === to ? (
              <span className="quick-link quick-link--current" key={to} aria-current="page">
                <Icon size={15} strokeWidth={2} />
                {label}
              </span>
            ) : (
              <NavLink className="quick-link" to={to} key={to} end>
                <Icon size={15} strokeWidth={2} />
                {label}
              </NavLink>
            )
          ))}
        </nav>
      )}
      <nav className="quick-links" aria-label="Accès rapide">
        {LINKS.map(({ to, label, Icon, inIconNav, inSidebar }) => {
          const current = pathname === to || pathname.startsWith(`${to}/`);
          if (current) {
            return (
              <span className={linkClass(inIconNav, inSidebar, "quick-link--current")} key={to} aria-current="page">
                <Icon size={15} strokeWidth={2} />
                {label}
              </span>
            );
          }
          return (
            <NavLink className={linkClass(inIconNav, inSidebar)} to={to} key={to}>
              <Icon size={15} strokeWidth={2} />
              {label}
            </NavLink>
          );
        })}
      </nav>
    </>
  );
}
