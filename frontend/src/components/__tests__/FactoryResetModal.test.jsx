import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import FactoryResetModal from "../FactoryResetModal";
import { farmApi } from "../../api/endpoints";

// The confirm step used to disable "Réinitialiser la ferme" whenever the typed farm name
// didn't match — clicking did nothing and nothing said why. Now the button is always
// clickable and every failing guard produces a visible message.

vi.mock("../../api/endpoints", () => ({
  farmApi: { reset: vi.fn(), resetConfirm: vi.fn(), resetRequest: vi.fn() },
}));
vi.mock("../../api/errors", () => ({ getServerErrorMessage: (_e, fb) => fb }));
vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ user: { farm_name: "Ferme Test" }, logout: vi.fn() }),
}));

async function toConfirmStep() {
  render(<FactoryResetModal open mode="dashboard" onClose={() => {}} />);
  await userEvent.click(await screen.findByRole("button", { name: "Continuer" }));
  return screen.findByRole("button", { name: "Réinitialiser la ferme" });
}

describe("FactoryResetModal — the confirm step always says what's wrong", () => {
  beforeEach(() => vi.clearAllMocks());

  test("a wrong farm name shows an inline mismatch hint and a message on click, and does not reset", async () => {
    const btn = await toConfirmStep();
    const nameInput = screen.getByRole("textbox");
    await userEvent.type(nameInput, "Ferme Tset"); // typo

    expect(screen.getByText(/Ne correspond pas au nom exact/i)).toBeInTheDocument();

    await userEvent.click(btn);
    expect(screen.getByText(/ne correspond pas au nom exact de la ferme/i)).toBeInTheDocument();
    expect(farmApi.reset).not.toHaveBeenCalled();
  });

  test("correct name but empty password → explicit message, no reset", async () => {
    const btn = await toConfirmStep();
    await userEvent.type(screen.getByRole("textbox"), "Ferme Test");
    await userEvent.click(btn);
    expect(screen.getByText(/Saisissez votre mot de passe/i)).toBeInTheDocument();
    expect(farmApi.reset).not.toHaveBeenCalled();
  });

  test("correct name + password → calls farmApi.reset", async () => {
    farmApi.reset.mockResolvedValue({ data: {} });
    const btn = await toConfirmStep();
    await userEvent.type(screen.getByRole("textbox"), "Ferme Test");
    await userEvent.type(screen.getByLabelText(/mot de passe/i), "s3cret");
    await userEvent.click(btn);
    expect(farmApi.reset).toHaveBeenCalledWith("s3cret");
  });
});
