import React from "react";
import { render, screen } from "@testing-library/react";
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
    expect(screen.getByRole("button", { name: /stock/i })).toBeInTheDocument();
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
