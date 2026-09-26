import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
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

// A tiny in-memory history: each wizard step is its own history entry since campaign 9 (B15 —
// the phone's back button left the page from any step), so navigating to the same path pushes
// an entry carrying the step, navigate(-1) steps back, and any other path is just recorded.
const PAGE = "/onboarding/protocol";
const { navigateMock, fakeHistory } = vi.hoisted(() => {
  const listeners = new Set();
  let entries;
  let index;
  const emit = () => listeners.forEach((l) => l());
  const fakeHistory = {
    reset() { entries = [{ pathname: "/onboarding/protocol", search: "", state: null }]; index = 0; },
    current: () => entries[index],
    subscribe: (l) => { listeners.add(l); return () => listeners.delete(l); },
  };
  fakeHistory.reset();
  const navigateMock = vi.fn((to, opts) => {
    if (typeof to === "number") { index = Math.max(0, Math.min(entries.length - 1, index + to)); emit(); return; }
    if (to === entries[index].pathname) {
      entries = [...entries.slice(0, index + 1), { pathname: to, search: "", state: opts?.state ?? null }];
      index += 1;
      emit();
    }
  });
  return { navigateMock, fakeHistory };
});
vi.mock("react-router-dom", async () => {
  const { useSyncExternalStore } = await import("react");
  return {
    useNavigate: () => navigateMock,
    useLocation: () => useSyncExternalStore(fakeHistory.subscribe, fakeHistory.current),
  };
});
beforeEach(() => fakeHistory.reset());
const leftThePage = () => navigateMock.mock.calls.filter(([to]) => typeof to === "string" && to !== PAGE);
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

// Batch creation opens on the header step and the method choice (2026-09-11) before the
// protocol form itself. Everything below that used to start at the form now walks through
// them first — the batch name comes from this step now, not from the form's own field.
async function goToManualForm({ productionType } = {}) {
  await userEvent.type(screen.getByRole("textbox", { name: /nom de la bande/i }), "Bande test");
  await userEvent.type(screen.getByRole("spinbutton", { name: /poussins mis en place/i }), "500");
  await userEvent.type(screen.getByRole("textbox", { name: /nom du bâtiment/i }), "Bâtiment A");
  if (productionType) {
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /type de protocole/i }), productionType);
  }
  await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
  await userEvent.click(screen.getByRole("button", { name: /Configurer manuellement/i }));
}

describe("OnboardingProtocolPage — true first-time onboarding (is_configured: false)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuth.mockReturnValue({ user: { is_configured: false }, refreshMe: vi.fn() });
    mockOnboardingContext();
  });

  test("shows the multi-batch 'add another' button, not the add-house 'Créer la bande' label", async () => {
    render(<OnboardingProtocolPage />);
    await goToManualForm();
    expect(screen.getByRole("button", { name: "Ajouter ce bâtiment et en configurer un autre" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Suivant" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Créer la bande" })).not.toBeInTheDocument();
  });

  test("adding a house via 'Ajouter ce bâtiment...' submits it, lists it, and resets the form for another", async () => {
    onboardingApi.submit.mockResolvedValue({ data: { house: { houseCode: "H-1", name: "Poulailler Nord" } } });
    render(<OnboardingProtocolPage />);
    await goToManualForm();

    await userEvent.click(screen.getByRole("button", { name: /charger le modèle de départ/i }));
    await userEvent.click(screen.getByRole("button", { name: "Ajouter ce bâtiment et en configurer un autre" }));

    await waitFor(() => expect(onboardingApi.submit).toHaveBeenCalledTimes(1));
    // Stayed on this page — no navigation away happened for "add another".
    expect(leftThePage()).toEqual([]);
    // Running list shows the just-added house, and a way to move on without adding more.
    expect(await screen.findByText("Poulailler Nord")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continuer sans ajouter d'autre bâtiment" })).toBeInTheDocument();

    // Form reset for the next house: the starter template's rows are gone, "Suivant" disabled again.
    expect(screen.getByRole("button", { name: "Suivant" })).toBeDisabled();
  });

  test("'Continuer sans ajouter d'autre bâtiment' navigates to the Stock step without submitting again", async () => {
    onboardingApi.submit.mockResolvedValue({ data: { house: { houseCode: "H-1", name: "Bâtiment A" } } });
    render(<OnboardingProtocolPage />);
    await goToManualForm();

    await userEvent.click(screen.getByRole("button", { name: /charger le modèle de départ/i }));
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

  test("shows 'Créer la bande', not the multi-batch 'add another' button", async () => {
    render(<OnboardingProtocolPage />);
    await goToManualForm();
    expect(screen.getByRole("button", { name: "Créer la bande" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ajouter ce bâtiment et en configurer un autre" })).not.toBeInTheDocument();
  });

  test("'Créer la bande' submits and returns to the dashboard, not the wizard's next step", async () => {
    onboardingApi.submit.mockResolvedValue({ data: { house: { houseCode: "H-1", name: "Bâtiment A" } } });
    render(<OnboardingProtocolPage />);
    await goToManualForm({ productionType: "LAYER" });

    await userEvent.click(screen.getByRole("button", { name: /charger le modèle de départ/i }));
    await userEvent.click(screen.getByRole("button", { name: "Créer la bande" }));

    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/dashboard", { replace: true }));
    expect(navigateMock).not.toHaveBeenCalledWith("/onboarding/stock");
  });

  // production_type had no UI at all before the header step — onboarding always sent
  // "BROILER". What the user picks must actually reach the submitted payload.
  test("submits the protocol type picked in the header step, and the header's own fields", async () => {
    onboardingApi.submit.mockResolvedValue({ data: { house: { houseCode: "H-1", name: "Bâtiment A" } } });
    render(<OnboardingProtocolPage />);
    await goToManualForm({ productionType: "LAYER" });

    await userEvent.click(screen.getByRole("button", { name: /charger le modèle de départ/i }));
    await userEvent.click(screen.getByRole("button", { name: "Créer la bande" }));

    await waitFor(() => expect(onboardingApi.submit).toHaveBeenCalledTimes(1));
    expect(onboardingApi.submit.mock.calls[0][0]).toMatchObject({
      house: { name: "Bâtiment A", maxCapacity: 500 },
      batch: { name: "Bande test", productionType: "LAYER", initialCount: 500 },
    });
  });

  test("stepping back from the choice keeps what was typed in the header step", async () => {
    render(<OnboardingProtocolPage />);

    await userEvent.type(screen.getByRole("textbox", { name: /nom de la bande/i }), "Bande test");
    await userEvent.type(screen.getByRole("spinbutton", { name: /poussins mis en place/i }), "500");
    await userEvent.type(screen.getByRole("textbox", { name: /nom du bâtiment/i }), "Bâtiment A");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /type de protocole/i }), "LAYER");
    await userEvent.click(screen.getByRole("button", { name: "Suivant" }));

    await userEvent.click(screen.getByRole("button", { name: /Retour/i }));

    expect(screen.getByRole("textbox", { name: /nom de la bande/i })).toHaveValue("Bande test");
    expect(screen.getByRole("spinbutton", { name: /poussins mis en place/i })).toHaveValue(500);
    expect(screen.getByRole("textbox", { name: /nom du bâtiment/i })).toHaveValue("Bâtiment A");
    expect(screen.getByRole("combobox", { name: /type de protocole/i })).toHaveValue("LAYER");
  });

  test("the phone's back button steps back through the wizard instead of leaving it", async () => {
    render(<OnboardingProtocolPage />);
    await goToManualForm();
    expect(screen.getByRole("button", { name: /charger le modèle de départ/i })).toBeInTheDocument();

    act(() => navigateMock(-1)); // what the browser's back button does to the history
    expect(await screen.findByRole("button", { name: /Configurer manuellement/i })).toBeInTheDocument();
    act(() => navigateMock(-1));
    expect(await screen.findByRole("textbox", { name: /nom de la bande/i })).toHaveValue("Bande test");
    expect(leftThePage()).toEqual([]);
  });
});
