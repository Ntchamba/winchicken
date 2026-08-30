import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";
import HouseProtocolForm from "../HouseProtocolForm";

// Part B (docs/deviations.md Part 15): the onboarding wizard's own "Suivant" button
// (HouseProtocolForm's save-bar button, labeled "Suivant" in mode="onboarding") must stay
// disabled until the protocol actually has at least one line — `disabled={saving ||
// totalRows === 0}`. This exercises the real button through a real user interaction
// ("Charger un modèle" seeds the starter template), not a synthetic prop.
describe("HouseProtocolForm — Suivant enables only once data is entered", () => {
  test("disabled with an empty protocol, enabled after loading the starter template", async () => {
    render(<HouseProtocolForm mode="onboarding" onSave={() => {}} />);

    const nextButton = screen.getByRole("button", { name: "Suivant" });
    expect(nextButton).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: /charger le modèle de départ/i }));

    expect(nextButton).toBeEnabled();
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
