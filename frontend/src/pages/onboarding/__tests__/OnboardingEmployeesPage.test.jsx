import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import OnboardingEmployeesPage from "../OnboardingEmployeesPage";
import { useAuth } from "../../../context/AuthContext";
import { useOnboarding } from "../../../context/OnboardingContext";

// Part B (docs/deviations.md Part 15): checked this page's actual Suivant/Sauter behavior
// before writing assertions — neither button is gated on entered employee data (this step is
// deliberately skippable per its own on-screen copy, "Facultatif"), only on the async
// save-in-progress state. What *is* real, data-dependent enable/disable on this page is the
// "Ajouter un autre employé" flow: it refuses to add an incomplete entry to the list rather
// than silently accepting it.

vi.mock("../../../context/AuthContext", () => ({ useAuth: vi.fn() }));
vi.mock("../../../context/OnboardingContext", () => ({ useOnboarding: vi.fn() }));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));

describe("OnboardingEmployeesPage", () => {
  const setEmployees = vi.fn();
  const refreshMe = vi.fn().mockResolvedValue({});

  beforeEach(() => {
    vi.clearAllMocks();
    useAuth.mockReturnValue({ refreshMe });
    useOnboarding.mockReturnValue({ employees: [], setEmployees });
  });

  test("Suivant/Sauter are enabled with no employees entered — this step is optional", () => {
    render(<OnboardingEmployeesPage />);
    expect(screen.getByRole("button", { name: "Sauter" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Suivant" })).toBeEnabled();
  });

  test("Sauter disables both buttons while it saves", async () => {
    render(<OnboardingEmployeesPage />);
    await userEvent.click(screen.getByRole("button", { name: "Sauter" }));
    await waitFor(() => expect(refreshMe).toHaveBeenCalled());
  });

  test("adding an employee with missing fields is rejected, not silently accepted", async () => {
    render(<OnboardingEmployeesPage />);
    await userEvent.type(screen.getByLabelText("Nom"), "Amina");
    // Email and password left blank on purpose.
    await userEvent.click(screen.getByRole("button", { name: /ajouter un autre employé/i }));

    expect(screen.getByText("Le nom, l'email et le mot de passe sont obligatoires.")).toBeInTheDocument();
    expect(setEmployees).not.toHaveBeenCalled();
  });

  test("adding a complete employee entry succeeds and clears the form", async () => {
    render(<OnboardingEmployeesPage />);
    await userEvent.type(screen.getByLabelText("Nom"), "Amina Ndoye");
    await userEvent.type(screen.getByLabelText("Email"), "amina@winchicken.test");
    await userEvent.type(screen.getByLabelText("Mot de passe"), "S3curePass!");
    await userEvent.click(screen.getByRole("button", { name: /ajouter un autre employé/i }));

    expect(setEmployees).toHaveBeenCalledWith([
      expect.objectContaining({ name: "Amina Ndoye", email: "amina@winchicken.test", role: "FARMER" }),
    ]);
  });
});
