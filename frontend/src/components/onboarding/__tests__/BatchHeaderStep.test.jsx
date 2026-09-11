import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";
import BatchHeaderStep from "../BatchHeaderStep";

describe("BatchHeaderStep — the small step that opens batch creation", () => {
  test("keeps 'Suivant' disabled until the batch name, the count and the building are filled", async () => {
    const user = userEvent.setup();
    render(<BatchHeaderStep onNext={() => {}} />);

    const next = screen.getByRole("button", { name: "Suivant" });
    expect(next).toBeDisabled();

    await user.type(screen.getByLabelText(/Nom de la bande/i), "Bande A");
    expect(next).toBeDisabled();
    await user.type(screen.getByLabelText(/Poussins mis en place/i), "500");
    expect(next).toBeDisabled();
    await user.type(screen.getByLabelText(/Nom du bâtiment/i), "Poulailler 1");
    expect(next).toBeEnabled();
  });

  test("a whitespace-only batch name does not enable 'Suivant'", async () => {
    const user = userEvent.setup();
    render(<BatchHeaderStep onNext={() => {}} />);

    await user.type(screen.getByLabelText(/Nom de la bande/i), "   ");
    await user.type(screen.getByLabelText(/Poussins mis en place/i), "500");
    await user.type(screen.getByLabelText(/Nom du bâtiment/i), "Poulailler 1");
    expect(screen.getByRole("button", { name: "Suivant" })).toBeDisabled();
  });

  test("hands the filled header up, with the protocol type the user picked", async () => {
    const user = userEvent.setup();
    const onNext = vi.fn();
    render(<BatchHeaderStep onNext={onNext} />);

    await user.type(screen.getByLabelText(/Nom de la bande/i), "Bande A");
    await user.type(screen.getByLabelText(/Poussins mis en place/i), "500");
    await user.type(screen.getByLabelText(/Nom du bâtiment/i), "Poulailler 1");
    await user.selectOptions(screen.getByLabelText(/Type de protocole/i), "LAYER");
    await user.click(screen.getByRole("button", { name: "Suivant" }));

    expect(onNext).toHaveBeenCalledWith(
      expect.objectContaining({
        batchName: "Bande A",
        chicksPlaced: "500",
        buildingName: "Poulailler 1",
        productionType: "LAYER",
      }),
    );
  });

  // The batch type has a backend field (PoultryBatch.production_type) but never had a UI —
  // onboarding hardcoded "BROILER". Broiler stays the default so the existing flow is unchanged
  // for anyone who doesn't touch the selector.
  test("defaults the protocol type to Poulet de chair (BROILER)", async () => {
    const user = userEvent.setup();
    const onNext = vi.fn();
    render(<BatchHeaderStep onNext={onNext} />);

    await user.type(screen.getByLabelText(/Nom de la bande/i), "Bande A");
    await user.type(screen.getByLabelText(/Poussins mis en place/i), "500");
    await user.type(screen.getByLabelText(/Nom du bâtiment/i), "Poulailler 1");
    await user.click(screen.getByRole("button", { name: "Suivant" }));

    expect(onNext).toHaveBeenCalledWith(expect.objectContaining({ productionType: "BROILER" }));
  });

  test("re-opens with what was already typed, so going back loses nothing", () => {
    render(
      <BatchHeaderStep
        initial={{ batchName: "Bande B", chicksPlaced: 900, buildingName: "Poulailler 2", productionType: "LAYER" }}
        onNext={() => {}}
      />,
    );

    expect(screen.getByLabelText(/Nom de la bande/i)).toHaveValue("Bande B");
    expect(screen.getByLabelText(/Poussins mis en place/i)).toHaveValue(900);
    expect(screen.getByLabelText(/Nom du bâtiment/i)).toHaveValue("Poulailler 2");
    expect(screen.getByLabelText(/Type de protocole/i)).toHaveValue("LAYER");
  });
});
