import React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import DashboardLayout from "../DashboardLayout";

// 2026-09-18 mobile audit, finding (1): the drawer toggle was rendered with an inline
// `display: "none"`, so on a phone there was no way to open the sidebar on any of the 18
// dashboard views — Finances, Stock, Employés, Paramètres, Déconnexion and Mes heures live
// only in the drawer, and all of them were unreachable.
//
// jsdom evaluates no media queries, so the *visibility* of the top bar is verified live by
// tools/responsive-audit at 375/768/1440. What belongs here is the behaviour: that the button
// exists without being hidden inline, and that opening, closing and navigating work.

vi.mock("../../api/endpoints", () => ({
  searchApi: { search: vi.fn().mockResolvedValue({ houses: [], batches: [], stockItems: [] }) },
  alertsApi: { list: vi.fn().mockResolvedValue([]), markRead: vi.fn(), markAllRead: vi.fn() },
  housesApi: { list: vi.fn().mockResolvedValue([]) },
  financeApi: { myHours: vi.fn().mockResolvedValue([]), logHours: vi.fn() },
  casesApi: { create: vi.fn() },
}));

const renderLayout = (props = {}) =>
  render(
    <DashboardLayout houses={[]} user={{ name: "Ada Test", role: "Administrateur" }} {...props}>
      <p>contenu</p>
    </DashboardLayout>,
  );

const toggle = () => screen.getByRole("button", { name: /ouvrir le menu/i });
const toggle_ariaExpanded = () => document.getElementById("sidebar-mobile-toggle").getAttribute("aria-expanded");
const sidebar = () => document.querySelector(".sidebar");

afterEach(() => {
  document.body.style.overflow = "";
});

describe("DashboardLayout mobile drawer", () => {
  test("renders a menu button that is not hidden inline", () => {
    renderLayout();
    const button = toggle();
    // The regression itself: an inline display:none beat every media query.
    expect(button.style.display).toBe("");
    expect(button).toHaveAttribute("aria-controls", "dashboard-sidebar");
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  test("the menu button opens the sidebar as an overlay", async () => {
    const user = userEvent.setup();
    renderLayout();
    expect(sidebar().className).not.toMatch(/\bopen\b/);
    expect(document.querySelector(".sidebar-scrim")).toBeNull();

    await user.click(toggle());

    expect(sidebar().className).toMatch(/\bopen\b/);
    expect(document.querySelector(".sidebar-scrim")).not.toBeNull();
    // Two of them once open: the top bar's toggle relabels itself, and the drawer has its own.
    expect(screen.getAllByRole("button", { name: /fermer le menu/i })).toHaveLength(2);
    expect(toggle_ariaExpanded()).toBe("true");
    expect(document.body.style.overflow).toBe("hidden");
  });

  test("tapping the dimmed page closes it and restores page scrolling", async () => {
    const user = userEvent.setup();
    renderLayout();
    await user.click(toggle());

    await user.click(document.querySelector(".sidebar-scrim"));

    expect(sidebar().className).not.toMatch(/\bopen\b/);
    expect(document.body.style.overflow).toBe("");
  });

  test("Escape closes it", async () => {
    const user = userEvent.setup();
    renderLayout();
    await user.click(toggle());

    await user.keyboard("{Escape}");

    expect(sidebar().className).not.toMatch(/\bopen\b/);
  });

  test("the in-drawer close button closes it", async () => {
    const user = userEvent.setup();
    renderLayout();
    await user.click(toggle());

    await user.click(document.querySelector(".sidebar-close-button"));

    expect(sidebar().className).not.toMatch(/\bopen\b/);
  });

  test("a drawer link navigates and closes the drawer behind it", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    renderLayout({ onNavigate });
    await user.click(toggle());

    await user.click(screen.getByRole("button", { name: /paramètres/i }));

    expect(onNavigate).toHaveBeenCalledWith("/dashboard/settings");
    expect(sidebar().className).not.toMatch(/\bopen\b/);
  });

  test("the links that only exist in the drawer are reachable once it is open", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    const onLogout = vi.fn();
    renderLayout({ onNavigate, onLogout });
    await user.click(toggle());

    // The six the audit named as unreachable on a phone.
    expect(screen.getByRole("button", { name: /finances/i })).toBeInTheDocument();
    // Scoped to the drawer: the phone icon bar has its own "Stock" button (2026-09-23).
    expect(within(sidebar()).getByRole("button", { name: /stock/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /employés/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /paramètres/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /mes heures/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /déconnexion/i }));
    expect(onLogout).toHaveBeenCalled();
  });

  test("a route change closes the drawer even when it did not come from a drawer link", async () => {
    const user = userEvent.setup();
    const { rerender } = renderLayout({ activePath: "/dashboard" });
    await user.click(toggle());
    expect(sidebar().className).toMatch(/\bopen\b/);

    rerender(
      <DashboardLayout houses={[]} user={{ name: "Ada Test", role: "Administrateur" }} activePath="/dashboard/stock">
        <p>contenu</p>
      </DashboardLayout>,
    );

    expect(sidebar().className).not.toMatch(/\bopen\b/);
  });
});

// 2026-09-23: on a phone (≤600px, CSS-only; verified live at 375px) the top bar carries an
// icon-only nav. jsdom has no media queries, so this covers names and behaviour only.
describe("DashboardLayout phone icon navigation", () => {
  const iconNav = () => within(screen.getByRole("navigation", { name: "Navigation principale" }));

  test("every icon has a French accessible name", () => {
    renderLayout();
    const names = iconNav().getAllByRole("button").map((b) => b.getAttribute("aria-label"));
    expect(names).toEqual(["Bilan", "Finance", "Stock", "Bâtiment", "Calendrier", "Autres"]);
  });

  test.each([
    ["Bilan", "/dashboard/overview"],
    ["Finance", "/dashboard/finances"],
    ["Stock", "/dashboard/stock"],
    ["Bâtiment", "/dashboard/houses"],
    ["Calendrier", "/dashboard/calendar"],
  ])("%s navigates to %s", async (name, path) => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    renderLayout({ onNavigate });
    await user.click(iconNav().getByRole("button", { name: new RegExp(`^${name}`) }));
    expect(onNavigate).toHaveBeenCalledWith(path);
  });

  test("Autres opens the existing drawer with the remaining items", async () => {
    const user = userEvent.setup();
    renderLayout();
    const autres = iconNav().getByRole("button", { name: "Autres" });
    expect(autres).toHaveAttribute("aria-expanded", "false");
    await user.click(autres);
    expect(sidebar().className).toMatch(/\bopen\b/);
    expect(autres).toHaveAttribute("aria-expanded", "true");
    expect(within(sidebar()).getByRole("button", { name: /employés/i })).toBeInTheDocument();
  });

  test("the active icon is marked as the current page", () => {
    renderLayout({ activePath: "/dashboard/stock" });
    expect(iconNav().getByRole("button", { name: "Stock" })).toHaveAttribute("aria-current", "page");
    expect(iconNav().getByRole("button", { name: "Bilan" })).not.toHaveAttribute("aria-current");
  });

  test("badge counts are announced in the name", () => {
    renderLayout({ stockLowCount: 3 });
    expect(iconNav().getByRole("button", { name: "Stock, 3 en alerte" })).toBeInTheDocument();
  });

  test("Finance is hidden when the role cannot see it", () => {
    renderLayout({ canSeeFinance: false });
    expect(iconNav().queryByRole("button", { name: /^finance/i })).toBeNull();
  });
});
