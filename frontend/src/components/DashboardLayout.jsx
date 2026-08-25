import { Home, Wallet, Package, Users, Wallet2, Plus, Settings, LogOut, Bird, Egg, Menu, X } from "lucide-react";
import { useState } from "react";
import "../styles/house-protocol-theme-light.css";
import "../styles/dashboard-theme.css";
import "../styles/sidebar-theme.css";

/**
 * Sidebar + content shell for every /dashboard/* route. Rendered by DashboardShell.jsx, which
 * fetches `houses` from GET /api/houses/ and derives the `canSee*`/`canManageHouses` booleans
 * from GET /api/auth/me/'s `role` (cahier des charges section 8 permission matrix — a
 * disallowed sidebar link is hidden entirely, never just disabled).
 *
 * @param {Object[]} [houses] - `[{ houseCode, name, type }]`, one entry per PoultryHouse, used
 *   to render the "Bâtiments" sidebar section. `type` is currently always hardcoded to
 *   "Broiler" by DashboardShell (see its usage) regardless of the house's actual batches.
 * @param {Object} [user] - `{ name, role }` — display name and human-readable role label.
 * @param {string} [activePath] - Current route pathname, used to highlight the matching link.
 * @param {boolean} [canManageHouses] - Shows/hides the "+ Nouveau bâtiment" sidebar action.
 * @param {boolean} [canSeeFinance] - Shows/hides the "Finance" sidebar link. Defaults to true —
 *   every role sees the link since Finance access-detail spec 4.3/8: restricted roles get a
 *   reduced trend-only view server-side rather than the link being hidden.
 * @param {boolean} [canSeeEmployees] - Shows/hides the "Employés" sidebar link.
 * @param {boolean} [canSeeCashier] - Shows/hides the "Caissier" sidebar link.
 * @param {(path: string) => void} [onNavigate] - Called with a route path when a sidebar link
 *   (or the mobile menu) is clicked.
 * @param {() => void} [onLogout] - Called when "Déconnexion" is clicked.
 * @param {import('react').ReactNode} children - Page content rendered in `<main>`.
 */
export default function DashboardLayout({
  houses = [],
  user = { name: "Utilisateur", role: "Administrateur" },
  activePath = "/dashboard",
  canManageHouses = true,
  canSeeFinance = true,
  canSeeEmployees = true,
  canSeeCashier = true,
  onNavigate,
  onLogout,
  children,
}) {
  const [mobileOpen, setMobileOpen] = useState(false);

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
        <div className="sidebar-brand">
          <span className="brand-mark" style={{ width: 34, height: 34 }}>
            <img src="/logo-mark.png" alt="Winchicken" />
          </span>
          <div>
            <p className="eyebrow" style={{ marginBottom: 0 }}>WINCHICKEN</p>
          </div>
        </div>

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
                {house.name}
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
            Nouveau bâtiment
          </button>
        )}

        <div className="sidebar-divider" />

        <nav className="sidebar-nav">
          {canSeeFinance && (
            <button className={`sidebar-link ${isActive("/dashboard/finance") ? "active" : ""}`} onClick={() => go("/dashboard/finance")}>
              <Wallet size={16} strokeWidth={1.8} />
              Finance
            </button>
          )}
          <button className={`sidebar-link ${isActive("/dashboard/stock") ? "active" : ""}`} onClick={() => go("/dashboard/stock")}>
            <Package size={16} strokeWidth={1.8} />
            Stock
          </button>
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
        </nav>

        <div className="sidebar-spacer" />

        <nav className="sidebar-bottom-nav">
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
      </aside>

      <main className="dashboard-content">{children}</main>
    </div>
  );
}
