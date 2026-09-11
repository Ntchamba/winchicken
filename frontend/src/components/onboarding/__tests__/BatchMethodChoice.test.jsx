import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";
import BatchMethodChoice from "../BatchMethodChoice";

describe("BatchMethodChoice — how the user wants to fill the protocol", () => {
  test("offers both methods and routes each one to its own handler", async () => {
    const user = userEvent.setup();
    const onSelectManual = vi.fn();
    const onSelectExcel = vi.fn();
    render(<BatchMethodChoice onSelectManual={onSelectManual} onSelectExcel={onSelectExcel} onBack={() => {}} />);

    await user.click(screen.getByRole("button", { name: /Configurer manuellement/i }));
    expect(onSelectManual).toHaveBeenCalledTimes(1);
    expect(onSelectExcel).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /Importer via Excel/i }));
    expect(onSelectExcel).toHaveBeenCalledTimes(1);
  });

  test("can go back to the previous step", async () => {
    const user = userEvent.setup();
    const onBack = vi.fn();
    render(<BatchMethodChoice onSelectManual={() => {}} onSelectExcel={() => {}} onBack={onBack} />);

    await user.click(screen.getByRole("button", { name: /Retour/i }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });
});
