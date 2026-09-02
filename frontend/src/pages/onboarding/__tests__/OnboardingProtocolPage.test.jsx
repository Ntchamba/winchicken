import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import OnboardingProtocolPage from "../OnboardingProtocolPage";
import { useAuth } from "../../../context/AuthContext";
import { useOnboarding } from "../../../context/OnboardingContext";
import { onboardingApi } from "../../../api/endpoints";

// Multi-batch first-time onboarding (2026-08-27, docs/deviations.md) — exercised as a real
// rendered component tree (real HouseProtocolForm, real "Charger le modèle de départ" click to
// populate a real row), only the network/router/context boundaries mocked — matching this
// project's existing HouseProtocolForm.test.jsx convention ("a real button through a real user
// interaction, not a synthetic prop"). Not tested against the live single-farm dev stack: doing
// so would require a genuinely unconfigured farm, and this project only ever has one farm
// (Farm.singleton_lock) — the real farm here already carries real manual-testing data (incident
// reports, etc.) that a factory reset would destroy just to get an is_configured:false user.

const navigateMock = vi.fn();
vi.mock("react-router-dom", () => ({ useNavigate: () => navigateMock }));
vi.mock("../../../context/AuthContext", () => ({ useAuth: vi.fn() }));
vi.mock("../../../context/OnboardingContext", () => ({ useOnboarding: vi.fn() }));
vi.mock("../../../api/endpoints", () => ({
  onboardingApi: { submit: vi.fn() },
  protocolImportApi: { parse: vi.fn(), templateUrl: "" },
  stockApi: { addItem: vi.fn() },
  housesApi: { addProtocolCategory: vi.fn() },
}));

function mockOnboardingContext() {
  useOnboarding.mockReturnValue({
    houseHeader: {}, setHouseHeader: vi.fn(),
    categories: null, setCategories: vi.fn(),
    schedules: {}, setSchedules: vi.fn(),
  });
}

describe("OnboardingProtocolPage — true first-time onboarding (is_configured: false)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuth.mockReturnValue({ user: { is_configured: false }, refreshMe: vi.fn() });
    mockOnboardingContext();
  });

  test("shows the multi-batch 'add another' button, not the add-house 'Créer la bande' label", () => {
    render(<OnboardingProtocolPage />);
    expect(screen.getByRole("button", { name: "Ajouter ce bâtiment et en configurer un autre" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Suivant" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Créer la bande" })).not.toBeInTheDocument();
  });

  test("adding a house via 'Ajouter ce bâtiment...' submits it, lists it, and resets the form for another", async () => {
    onboardingApi.submit.mockResolvedValue({ data: { house: { houseCode: "H-1", name: "Poulailler Nord" } } });
    render(<OnboardingProtocolPage />);

    await userEvent.click(screen.getByRole("button", { name: /charger le modèle de départ/i }));
    // Part A: the submit buttons are disabled until the batch has a name.
    await userEvent.type(screen.getByRole("textbox", { name: /nom de la bande/i }), "Bande test");
    await userEvent.click(screen.getByRole("button", { name: "Ajouter ce bâtiment et en configurer un autre" }));

    await waitFor(() => expect(onboardingApi.submit).toHaveBeenCalledTimes(1));
    // Stayed on this step — no navigation happened for "add another".
    expect(navigateMock).not.toHaveBeenCalled();
    // Running list shows the just-added house, and a way to move on without adding more.
    expect(await screen.findByText("Poulailler Nord")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continuer sans ajouter d'autre bâtiment" })).toBeInTheDocument();

    // Form reset for the next house: the starter template's rows are gone, "Suivant" disabled again.
    expect(screen.getByRole("button", { name: "Suivant" })).toBeDisabled();
  });

  test("'Continuer sans ajouter d'autre bâtiment' navigates to the Stock step without submitting again", async () => {
    onboardingApi.submit.mockResolvedValue({ data: { house: { houseCode: "H-1", name: "Bâtiment A" } } });
    render(<OnboardingProtocolPage />);

    await userEvent.click(screen.getByRole("button", { name: /charger le modèle de départ/i }));
    // Part A: the submit buttons are disabled until the batch has a name.
    await userEvent.type(screen.getByRole("textbox", { name: /nom de la bande/i }), "Bande test");
    await userEvent.click(screen.getByRole("button", { name: "Ajouter ce bâtiment et en configurer un autre" }));
    await screen.findByText("Bâtiment A");

    await userEvent.click(screen.getByRole("button", { name: "Continuer sans ajouter d'autre bâtiment" }));

    expect(onboardingApi.submit).toHaveBeenCalledTimes(1); // still just the one "add another" call
    expect(navigateMock).toHaveBeenCalledWith("/onboarding/stock");
  });
});

describe("OnboardingProtocolPage — '+ Nouvelle bande' add-house flow (is_configured: true)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuth.mockReturnValue({ user: { is_configured: true }, refreshMe: vi.fn().mockResolvedValue({}) });
    mockOnboardingContext();
  });

  test("shows 'Créer la bande', not the multi-batch 'add another' button", () => {
    render(<OnboardingProtocolPage />);
    expect(screen.getByRole("button", { name: "Créer la bande" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ajouter ce bâtiment et en configurer un autre" })).not.toBeInTheDocument();
  });

  test("'Créer la bande' submits and returns to the dashboard, not the wizard's next step", async () => {
    onboardingApi.submit.mockResolvedValue({ data: { house: { houseCode: "H-1", name: "Bâtiment A" } } });
    render(<OnboardingProtocolPage />);

    await userEvent.click(screen.getByRole("button", { name: /charger le modèle de départ/i }));
    // Part A: the submit buttons are disabled until the batch has a name.
    await userEvent.type(screen.getByRole("textbox", { name: /nom de la bande/i }), "Bande test");
    await userEvent.click(screen.getByRole("button", { name: "Créer la bande" }));

    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/dashboard", { replace: true }));
    expect(navigateMock).not.toHaveBeenCalledWith("/onboarding/stock");
  });
});
