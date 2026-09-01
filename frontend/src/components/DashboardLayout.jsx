import { Calendar, ClipboardCheck, FileClock, Home, Wallet, Package, Users, Wallet2, Plus, Settings, LogOut, Bird, Egg, Menu, X, HelpCircle, Truck, ChevronDown } from "lucide-react";
import { useState } from "react";
import "../styles/house-protocol-theme-light.css";
import "../styles/dashboard-theme.css";
import "../styles/sidebar-theme.css";
import FireflyField from "./FireflyField";
import NotificationBell from "./NotificationBell";
import SidebarSearch from "./SidebarSearch";
import IncidentShortcut from "./IncidentShortcut";
import MyHoursShortcut from "./MyHoursShortcut";
import packageJson from "../../package.json";

// "Finances" accordion sub-items (2026-08-27, Finances restructure Part A) — all four resolve
// to sections within the single /dashboard/finances page via a URL hash anchor, never a
// separate route (see FinancesPage.jsx, which scrolls to the matching section id on hash
// change) — clicking one never navigates away from /dashboard/finances.
const FINANCES_SECTIONS = [
  { hash: "ventes", label: "Ventes" },
  { hash: "achats", label: "Achats" },
  { hash: "salaires", label: "Salaires" },
  { hash: "globale", label: "Globale" },
];

/**
 * Sidebar + content shell for every /dashboard/* route. Rendered by DashboardShell.jsx, which
 * fetches `houses` from GET /api/houses/ and derives the `canSee*`/`canManageHouses` booleans
 * from GET /api/auth/me/'s `role` (cahier des charges section 8 permission matrix — a
 * disallowed sidebar link is hidden entirely, never just disabled).
 *
 * @param {Object[]} [houses] - `[{ houseCode, name, type, activeBatchName }]`, one entry per
 *   PoultryHouse, used to render the "Bâtiments" sidebar section. A house with an active batch
 *   shows that batch's name as the primary label (the house identifier demoted to a small
 *   secondary line underneath, 2026-08-25 bugfix — the sidebar used to always show the house
 *   identifier, never the batch); a house with no active batch (sanitary void) falls back to
 *   the house name/identifier alone, since there's no batch name to show.
 * @param {Object} [user] - `{ name, role }` — display name and human-readable role label.
 * @param {string} [activePath] - Current route pathname, used to highlight the matching link.
 * @param {string} [activeHash] - Current `location.hash` (e.g. "#ventes"), used to highlight the
 *   active "Finances" sub-item (2026-08-27, Finances restructure) — threaded down from
 *   DashboardShellContent's own `useLocation()` rather than this component reading routing
 *   state itself, matching this file's existing "routing stays owned by the caller" convention
 *   (see SidebarSearch.jsx's docstring).
 * @param {boolean} [canManageHouses] - Shows/hides the "+ Nouvelle bande" sidebar action.
 * @param {boolean} [canSeeFinance] - Shows/hides the "Finances" sidebar section. Defaults to
 *   true — every role sees it since Finance access-detail spec 4.3/8: restricted roles get a
 *   reduced trend-only view server-side rather than the link being hidden.
 * @param {boolean} [canSeeSalaires] - Shows/hides the "Salaires" sidebar sub-item specifically
 *   (within the Finances accordion). Defaults to false — unlike Ventes/Achats/Globale, Salaires
 *   has no restricted view; it's hidden entirely for non-Admin/Farm-Manager roles, both here and
 *   in the matching section render on FinancesPage.jsx, with the real enforcement server-side
 *   (SalaryPaymentListView etc. are all IsAdminOrFarmManager).
 * @param {boolean} [canSeeEmployees] - Shows/hides the "Employés" sidebar link.
 * @param {boolean} [canSeeCashier] - Shows/hides the "Caissier" sidebar link.
 * @param {boolean} [canSeePurchaseOrders] - Shows/hides the "Commandes fournisseurs" sidebar
 *   link (2026-08-27, purchase-order task) — same role set that can create/receive/cancel
 *   orders server-side (Admin/Farm Manager/Cashier); GET itself stays open to any authenticated
 *   user (unchanged), this only hides the entry point for roles that couldn't act on it anyway.
 * @param {number} [unreadCount] - Notification-bell badge count (2026-08-26).
 * @param {number} [stockLowCount] - "Stock" link badge (danger-toned, hidden at 0).
 * @param {number} [financePendingCount] - "Finance" link badge (warning-toned, hidden at 0) —
 *   the caller only fetches this for Admin/Farm Manager (see useSidebarNotifications), so it's
 *   already 0 for every other role; no separate visibility flag needed here.
 * @param {number} [openCasesCount] - "Signaler un cas" badge (2026-08-27, Part B pulse
 *   treatment) — unresolved `UnusualCase` + open `EquipmentFault` count, hidden/not pulsing at 0.
 * @param {() => void} [onCountsChanged] - Called after a bell mark-read action, so the caller
 *   can refetch the shared counts.
 * @param {(path: string) => void} [onNavigate] - Called with a route path when a sidebar link
 *   (or the mobile menu) is clicked.
 * @param {() => void} [onLogout] - Called when "Déconnexion" is clicked.
 * @param {import('react').ReactNode} children - Page content rendered in `<main>`.
 */
export default function DashboardLayout({
  houses = [],
  user = { name: "Utilisateur", role: "Administrateur" },
  activePath = "/dashboard",
  activeHash = "",
  canManageHouses = true,
  canSeeFinance = true,
  canSeeSalaires = false,
  canSeeEmployees = true,
  canSeeCashier = true,
  canSeePurchaseOrders = true,
  canSeeAudit = false,
  unreadCount = 0,
  stockLowCount = 0,
  financePendingCount = 0,
  openCasesCount = 0,
  onCountsChanged,
  onNavigate,
  onLogout,
  children,
}) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [financesOpen, setFinancesOpen] = useState(() => activePath.startsWith("/dashboard/finances"));

  const isActive = (path) => activePath === path || (path !== "/dashboard" && activePath.startsWith(path));

  const go = (path) => {
    setMobileOpen(false);
    onNavigate?.(path);
  };

  return (
    <div className="dashboard-shell">
      <button
        className="sidebar-link-ghost"
        style={{ position: "fixed", top: 12, left: 12, zIndex: 50, display: "none" }}
        id="sidebar-mobile-toggle"
        onClick={() => setMobileOpen((v) => !v)}
        aria-label="Ouvrir le menu"
      >
        {mobileOpen ? <X size={16} /> : <Menu size={16} />}
      </button>

      <aside className={`sidebar ${mobileOpen ? "open" : ""}`}>
        <FireflyField className="sidebar-fireflies" />
        <div className="sidebar-brand-row">
          <div className="sidebar-brand">
            <span className="brand-mark" style={{ width: 34, height: 34 }}>
              <img src="/logo-mark.png" alt="Winchicken" />
            </span>
            <div>
              <p className="eyebrow" style={{ marginBottom: 0 }}>WINCHICKEN</p>
            </div>
          </div>
          <NotificationBell unreadCount={unreadCount} onCountsChanged={onCountsChanged} />
        </div>

        <SidebarSearch onNavigate={go} />

        <button className="sidebar-link active" style={{ marginBottom: 4 }} onClick={() => go("/dashboard")}>
          <Home size={16} strokeWidth={1.8} />
          Vue d'ensemble
        </button>

        <p className="sidebar-section-label">Bâtiments</p>
        <nav className="sidebar-nav">
          {houses.map((house) => {
            const Icon = house.type === "Layer" ? Egg : Bird;
            const path = `/dashboard/houses/${house.houseCode}`;
            return (
              <button key={house.houseCode} className={`sidebar-link ${isActive(path) ? "active" : ""}`} onClick={() => go(path)}>
                <Icon size={16} strokeWidth={1.8} />
                {house.activeBatchName ? (
                  <span className="sidebar-link-label">
                    <span className="sidebar-link-primary">{house.activeBatchName}</span>
                    <span className="sidebar-link-secondary">{house.name}</span>
                  </span>
                ) : (
                  house.name
                )}
              </button>
            );
          })}
          {houses.length === 0 && (
            <p style={{ margin: "4px 10px", fontSize: 12.5, color: "var(--muted)" }}>Aucun bâtiment configuré</p>
          )}
        </nav>
        {canManageHouses && (
          <button className="sidebar-link-ghost" onClick={() => go("/onboarding/protocol")}>
            <Plus size={14} strokeWidth={2.2} />
            Nouvelle bande
          </button>
        )}

        <div className="sidebar-divider" />

        <nav className="sidebar-nav">
          {canSeeFinance && (
            <>
              <button
                className={`sidebar-link ${isActive("/dashboard/finances") ? "active" : ""}`}
                onClick={() => setFinancesOpen((v) => !v)}
              >
                <Wallet size={16} strokeWidth={1.8} />
                Finances
                {financePendingCount > 0 && <span className="sidebar-link-badge warning">{financePendingCount}</span>}
                <ChevronDown size={14} strokeWidth={2} className={`sidebar-accordion-chevron ${financesOpen ? "open" : ""}`} />
              </button>
              {financesOpen && (
                <div className="sidebar-submenu">
                  {FINANCES_SECTIONS.filter((section) => section.hash !== "salaires" || canSeeSalaires).map((section) => (
                    <button
                      key={section.hash}
                      className={`sidebar-sublink ${isActive("/dashboard/finances") && activeHash === `#${section.hash}` ? "active" : ""}`}
                      onClick={() => go(`/dashboard/finances#${section.hash}`)}
                    >
                      {section.label}
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
          <button className={`sidebar-link ${isActive("/dashboard/stock") ? "active" : ""}`} onClick={() => go("/dashboard/stock")}>
            <Package size={16} strokeWidth={1.8} />
            Stock
            {stockLowCount > 0 && <span className="sidebar-link-badge danger">{stockLowCount}</span>}
          </button>
          {canSeePurchaseOrders && (
            <button className={`sidebar-link ${isActive("/dashboard/purchase-orders") ? "active" : ""}`} onClick={() => go("/dashboard/purchase-orders")}>
              <Truck size={16} strokeWidth={1.8} />
              Commandes fournisseurs
            </button>
          )}
          {canSeeEmployees && (
            <button className={`sidebar-link ${isActive("/dashboard/employees") ? "active" : ""}`} onClick={() => go("/dashboard/employees")}>
              <Users size={16} strokeWidth={1.8} />
              Employés
            </button>
          )}
          {canSeeCashier && (
            <button className={`sidebar-link ${isActive("/dashboard/cashier") ? "active" : ""}`} onClick={() => go("/dashboard/cashier")}>
              <Wallet2 size={16} strokeWidth={1.8} />
              Caissier
            </button>
          )}
          <button className={`sidebar-link ${isActive("/dashboard/calendar") ? "active" : ""}`} onClick={() => go("/dashboard/calendar")}>
            <Calendar size={16} strokeWidth={1.8} />
            Calendrier
          </button>
          {/* Open to every role, not gated (2026-08-26) — anyone can have a task assigned to
              them (Part E), including roles with no other sidebar links of their own. */}
          <button className={`sidebar-link ${isActive("/dashboard/my-tasks") ? "active" : ""}`} onClick={() => go("/dashboard/my-tasks")}>
            <ClipboardCheck size={16} strokeWidth={1.8} />
            Mes tâches
          </button>
          {/* Same "open to every role" reasoning as "Mes tâches" above — anyone can self-report
              their own hours, including roles with no other Finances access at all. */}
          <MyHoursShortcut />
        </nav>

        <IncidentShortcut houses={houses} openCasesCount={openCasesCount} />

        <div className="sidebar-spacer" />

        <nav className="sidebar-bottom-nav">
          {/* Single link, not a menu (2026-08-26): the only user-facing doc actually available
              is the protocol configuration guide — the two .docx spec documents in the repo
              root are explicitly addressed to the dev team ("à donner à Claude Code"), not farm
              staff, so they're deliberately not linked here. See docs/deviations.md Part 13. */}
          <a
            className="sidebar-link"
            href="/docs/protocol-configuration-usage-guide.pdf"
            target="_blank"
            rel="noopener noreferrer"
          >
            <HelpCircle size={16} strokeWidth={1.8} />
            Aide
          </a>
          {canSeeAudit && (
            <button className={`sidebar-link ${isActive("/dashboard/audit") ? "active" : ""}`} onClick={() => go("/dashboard/audit")}>
              <FileClock size={16} strokeWidth={1.8} />
              Journal d'audit
            </button>
          )}
          <button className="sidebar-link" onClick={() => go("/dashboard/settings")}>
            <Settings size={16} strokeWidth={1.8} />
            Paramètres
          </button>
          <button className="sidebar-link" onClick={onLogout}>
            <LogOut size={16} strokeWidth={1.8} />
            Déconnexion
          </button>
        </nav>

        <div className="sidebar-user">
          <span className="sidebar-user-avatar">
            {user.name.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase()}
          </span>
          <div>
            <p className="sidebar-user-name">{user.name}</p>
            <p className="sidebar-user-role">{user.role}</p>
          </div>
        </div>

        <p className="sidebar-version">v{packageJson.version}</p>
      </aside>

      <main className="dashboard-content">{children}</main>
    </div>
  );
}
