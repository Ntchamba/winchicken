import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import HouseProtocolForm from "../HouseProtocolForm";
import StockParametersForm from "../StockParametersForm";

// FIX 8, group 3. Both of these forms `await onSave(...)` with no catch, and all three callers
// (OnboardingProtocolPage, OnboardingStockPage, HouseProtocolPage) were `try {} finally {}`
// with no catch either — so a rejected save escaped as an unhandled promise rejection: the
// wizard did not advance, nothing was said, and the user had just typed a whole protocol or a
// whole warehouse. The catch belongs in the form, which owns the save bar.

vi.mock("../../api/endpoints", () => ({
  protocolImportApi: { parse: vi.fn(), templateUrl: "http://test/protocols/import-template.xlsx" },
  stockApi: { addItem: vi.fn(), addCategory: vi.fn(), addSupplier: vi.fn() },
  housesApi: { addProtocolCategory: vi.fn() },
}));

describe("HouseProtocolForm — a rejected save", () => {
  const fillProtocol = async (user) => {
    await user.click(screen.getByRole("button", { name: /charger le modèle de départ/i }));
    await user.type(screen.getByRole("textbox", { name: /nom de la bande/i }), "Bande printemps");
  };

  test("shows the server's message instead of failing silently", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockRejectedValue({ response: { data: { detail: "Bâtiment déjà configuré." } } });
    render(<HouseProtocolForm mode="onboarding" onSave={onSave} />);
    await fillProtocol(user);
    await user.click(screen.getByRole("button", { name: "Suivant" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bâtiment déjà configuré.");
  });

  test("an unreachable server is worded as such", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockRejectedValue({ code: "ECONNABORTED" }); // axios timeout: no response
    render(<HouseProtocolForm mode="onboarding" onSave={onSave} />);
    await fillProtocol(user);
    await user.click(screen.getByRole("button", { name: "Suivant" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Le serveur est inaccessible.");
  });

  test("keeps every protocol line on screen so nothing has to be retyped", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockRejectedValue({ response: { data: { detail: "Erreur." } } });
    render(<HouseProtocolForm mode="onboarding" onSave={onSave} />);
    await fillProtocol(user);
    await user.click(screen.getByRole("button", { name: "Suivant" }));
    await screen.findByRole("alert");
    expect(screen.getByRole("textbox", { name: /nom de la bande/i })).toHaveValue("Bande printemps");
    expect(screen.getByRole("button", { name: "Suivant" })).toBeEnabled();
  });
});

describe("StockParametersForm — a rejected save", () => {
  // `initialData` is keyed by category id (what `buildStockRows` returns), not a flat list.
  const ROWS = {
    1: [{
      key: "r1", itemCode: "FEE-1", name: "Provende", categoryId: 1, unit: "kg", quantity: "120",
      alertThreshold: "10", unitPrice: "450", supplierId: "", date: "2026-09-16", originalQuantity: 0,
    }],
  };
  const CATEGORIES = [{ id: 1, label: "Aliment", kind: "FEED" }];

  beforeEach(() => vi.clearAllMocks());

  test("the onboarding step says why it did not advance", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockRejectedValue({ response: { data: { detail: "Entrepôt invalide." } } });
    render(
      <StockParametersForm
        mode="onboarding" farmId={1} initialData={ROWS} initialCategories={CATEGORIES}
        initialSuppliers={[]} onSave={onSave} showStockEntry
      />,
    );
    await user.click(screen.getByRole("button", { name: "Suivant" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Entrepôt invalide.");
  });

  test("the management mode shows the error where 'Enregistré' would have gone", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockRejectedValue({ code: "ECONNABORTED" });
    render(
      <StockParametersForm
        mode="management" farmId={1} initialData={ROWS} initialCategories={CATEGORIES}
        initialSuppliers={[]} onSave={onSave}
      />,
    );
    await user.click(screen.getByRole("button", { name: /Enregistrer les paramètres/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Le serveur est inaccessible.");
    expect(screen.queryByText("Enregistré")).not.toBeInTheDocument();
  });
});
