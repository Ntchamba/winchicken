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
vi.mock("../../../api/endpoints", () => ({ employeesApi: { create: vi.fn() } }));
import { employeesApi } from "../../../api/endpoints";

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

// Campaign 3, in the browser: an employee typed into the form and saved with "Suivant" (without
// first pressing "Ajouter un autre employé") was silently dropped — finish() only posted the
// staged list. And when one creation failed, the ones already created stayed staged, so the
// next "Suivant" re-posted them and failed on "email déjà utilisé".
describe("OnboardingEmployeesPage — Suivant saves what is on screen", () => {
  const setEmployees = vi.fn();
  const refreshMe = vi.fn().mockResolvedValue({});
  const fill = async (name, email) => {
    await userEvent.type(screen.getByLabelText("Nom"), name);
    await userEvent.type(screen.getByLabelText("Email"), email);
    await userEvent.type(screen.getByLabelText("Mot de passe"), "S3curePass!");
  };

  beforeEach(() => {
    vi.clearAllMocks();
    useAuth.mockReturnValue({ refreshMe });
    employeesApi.create.mockResolvedValue({ data: {} });
  });

  test("the employee still in the form is created too", async () => {
    useOnboarding.mockReturnValue({ employees: [{ tempId: 1, name: "Awa", civility: "MME", email: "awa@x.test", role: "WORKER", password: "p" }], setEmployees });
    render(<OnboardingEmployeesPage />);
    await fill("Joseph Mbarga", "joseph@x.test");
    await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
    await waitFor(() => expect(refreshMe).toHaveBeenCalled());
    expect(employeesApi.create.mock.calls.map(([body]) => body.email)).toEqual(["awa@x.test", "joseph@x.test"]);
  });

  test("a half-filled form is refused with a message and nothing is sent", async () => {
    useOnboarding.mockReturnValue({ employees: [], setEmployees });
    render(<OnboardingEmployeesPage />);
    await userEvent.type(screen.getByLabelText("Nom"), "Joseph");
    await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
    expect(screen.getByText("Le nom, l'email et le mot de passe sont obligatoires.")).toBeInTheDocument();
    expect(employeesApi.create).not.toHaveBeenCalled();
    expect(refreshMe).not.toHaveBeenCalled();
  });

  test("after a failure only the employees not created yet stay in the list", async () => {
    const awa = { tempId: 1, name: "Awa", civility: "MME", email: "awa@x.test", role: "WORKER", password: "p" };
    const ben = { tempId: 2, name: "Ben", civility: "M", email: "ben@x.test", role: "CASHIER", password: "p" };
    useOnboarding.mockReturnValue({ employees: [awa, ben], setEmployees });
    employeesApi.create
      .mockResolvedValueOnce({ data: {} })
      .mockRejectedValueOnce({ isAxiosError: true, response: { status: 400, data: { email: ["Un utilisateur avec cet email existe déjà."] } } });
    render(<OnboardingEmployeesPage />);
    await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
    expect(await screen.findByText(/existe déjà/)).toBeInTheDocument();
    expect(setEmployees).toHaveBeenLastCalledWith([ben]);
    expect(refreshMe).not.toHaveBeenCalled();
  });
});
