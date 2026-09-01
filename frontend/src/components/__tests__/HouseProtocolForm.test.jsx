import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import HouseProtocolForm from "../HouseProtocolForm";

// Regression (2026-09-01): callers that don't pass `stockItems` (OnboardingProtocolPage,
// HouseProtocolPage) fell on a `stockItems = []` default — a fresh array identity every
// render — which made `useEffect(() => setStockItemList(stockItems), [stockItems])` re-fire
// on every render and spin into "Maximum update depth exceeded", freezing the page so the
// "Suivant" button and route changes never committed. The default is now a stable module
// constant. This pins that the no-prop render is loop-free.
describe("HouseProtocolForm — no infinite render loop without a stockItems prop", () => {
  afterEach(() => vi.restoreAllMocks());

  test("renders without stockItems and never hits max update depth", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(<HouseProtocolForm mode="onboarding" onSave={() => {}} />);
    expect(screen.getByRole("button", { name: "Suivant" })).toBeInTheDocument();
    const loopErrors = errorSpy.mock.calls
      .flat()
      .filter((a) => typeof a === "string" && a.includes("Maximum update depth"));
    expect(loopErrors).toEqual([]);
  });
});

// Part B (docs/deviations.md Part 15): the onboarding wizard's own "Suivant" button
// (HouseProtocolForm's save-bar button, labeled "Suivant" in mode="onboarding") must stay
// disabled until the protocol actually has at least one line — `disabled={saving ||
// totalRows === 0}`. This exercises the real button through a real user interaction
// ("Charger un modèle" seeds the starter template), not a synthetic prop.
describe("HouseProtocolForm — Suivant enables only once data is entered", () => {
  test("disabled with an empty protocol, enabled after a template AND a batch name", async () => {
    render(<HouseProtocolForm mode="onboarding" onSave={() => {}} />);

    const nextButton = screen.getByRole("button", { name: "Suivant" });
    expect(nextButton).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: /charger le modèle de départ/i }));
    // Part A: protocol rows alone are not enough — the batch name is now required.
    expect(nextButton).toBeDisabled();
    expect(screen.getByText("Le nom de la bande est requis.")).toBeInTheDocument();

    await userEvent.type(screen.getByRole("textbox", { name: /nom de la bande/i }), "Bande printemps");
    expect(nextButton).toBeEnabled();
  });

  test("a whitespace-only batch name does not enable Suivant", async () => {
    render(<HouseProtocolForm mode="onboarding" onSave={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: /charger le modèle de départ/i }));
    await userEvent.type(screen.getByRole("textbox", { name: /nom de la bande/i }), "   ");
    expect(screen.getByRole("button", { name: "Suivant" })).toBeDisabled();
  });
});

// Part B, "Modifier" modal requirements (docs/deviations.md Part 15): checked what this
// codebase actually has before writing assertions — there is no "Réinitialiser" button
// anywhere in this component or ProtocolEditModal (grepped both files; the only two
// "Annuler" buttons found are for canceling the add-category flow and the delete-category
// confirmation, unrelated sub-flows, not a form-level cancel/reset). What *is* real and
// regression-worthy: management mode must show the management save label and must never
// render the onboarding-only "Suivant" wizard button, and must load with the data it was
// given rather than blank fields.
describe("HouseProtocolForm — management mode (used by the \"Modifier\" modal)", () => {
  const initialHeader = {
    buildingName: "Bâtiment A", chicksPlaced: 500, growthCycle: 42, growthCycleUnit: "Day",
    batchName: "Bande Existante", weighingFrequency: "WEEK",
  };
  const initialCategories = [{ id: 1, label: "Alimentation", icon: "Soup" }];
  const initialSchedules = { 1: [{ id: 10, fromValue: 1, fromUnit: "Day", toValue: 15, toUnit: "Day", what: "Aliment démarrage", details: "" }] };

  test("shows the management save label, not the onboarding stepper button", () => {
    render(
      <HouseProtocolForm
        mode="management"
        houseCode="H-1"
        initialHeader={initialHeader}
        initialCategories={initialCategories}
        initialSchedules={initialSchedules}
        onSave={() => {}}
      />
    );

    expect(screen.getByRole("button", { name: "Enregistrer le protocole" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Suivant" })).not.toBeInTheDocument();
  });

  test("batchEditable=false disables the batch-scoped fields and shows a notice", () => {
    render(
      <HouseProtocolForm
        mode="management"
        houseCode="H-1"
        batchEditable={false}
        initialHeader={{ ...initialHeader, batchName: "" }}
        initialCategories={initialCategories}
        initialSchedules={initialSchedules}
        onSave={() => {}}
      />
    );

    expect(screen.getByText(/ce bâtiment n'a pas de bande active/i)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /nom de la bande/i })).toBeDisabled();
    // the house name stays editable — that IS persistable without a batch
    expect(screen.getByRole("textbox", { name: /nom du bâtiment/i })).toBeEnabled();
  });

  test("batchEditable defaults to true — no notice, band name editable", () => {
    render(
      <HouseProtocolForm
        mode="management"
        houseCode="H-1"
        initialHeader={initialHeader}
        initialCategories={initialCategories}
        initialSchedules={initialSchedules}
        onSave={() => {}}
      />
    );
    expect(screen.queryByText(/ce bâtiment n'a pas de bande active/i)).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /nom de la bande/i })).toBeEnabled();
  });

  test("loads with the existing protocol data, not empty fields", () => {
    render(
      <HouseProtocolForm
        mode="management"
        houseCode="H-1"
        initialHeader={initialHeader}
        initialCategories={initialCategories}
        initialSchedules={initialSchedules}
        onSave={() => {}}
      />
    );

    expect(screen.getByDisplayValue("Bâtiment A")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Bande Existante")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Aliment démarrage")).toBeInTheDocument();
    // Empty-protocol state would disable Suivant/Enregistrer (totalRows === 0) — asserting it's
    // enabled is an indirect but real check that the seeded row actually landed in state.
    expect(screen.getByRole("button", { name: "Enregistrer le protocole" })).toBeEnabled();
  });
});
