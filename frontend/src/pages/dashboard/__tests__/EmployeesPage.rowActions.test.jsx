import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import EmployeesPage from "../EmployeesPage";
import { employeesApi } from "../../../api/endpoints";

// FIX 8 group 5/6: the two per-row actions on this page (taux horaire, suppression) were
// `try {} finally {}` with no catch, so a rejected PATCH/DELETE left the row exactly as it
// was — identical to a tap that never registered. The page-level error line lives in the form
// card further down, so the message has to appear under the row itself.

vi.mock("../../../api/endpoints", () => ({
  employeesApi: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    setHourlyRate: vi.fn(),
    importXlsx: vi.fn(),
    importTemplateUrl: "http://test/employees/import-template.xlsx",
  },
}));
vi.mock("../../../hooks/useDocumentTitle", () => ({ default: vi.fn() }));

const EMPLOYEE = { id: 7, name: "Ouvrier 02", civility: "M", email: "ouvrier2@ferme.local", role: "WORKER", hourly_rate: null };

const typeRate = async (user, value) => {
  await user.type(await screen.findByLabelText("Taux horaire"), value);
};

describe("EmployeesPage — per-row actions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    employeesApi.list.mockResolvedValue({ data: [EMPLOYEE] });
  });

  test("a saved hourly rate is confirmed by naming the employee and the amount", async () => {
    const user = userEvent.setup();
    employeesApi.setHourlyRate.mockResolvedValue({ data: {} });
    render(<MemoryRouter><EmployeesPage /></MemoryRouter>);
    await typeRate(user, "750");
    await user.click(screen.getByTitle("Enregistrer le taux"));
    expect(await screen.findByRole("status")).toHaveTextContent("Taux horaire enregistré : 750 FCFA/h pour Ouvrier 02.");
  });

  test("a rejected hourly rate says why and keeps the typed value", async () => {
    const user = userEvent.setup();
    employeesApi.setHourlyRate.mockRejectedValue({ response: { data: { detail: "Taux horaire invalide." } } });
    render(<MemoryRouter><EmployeesPage /></MemoryRouter>);
    await typeRate(user, "750");
    await user.click(screen.getByTitle("Enregistrer le taux"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Taux horaire invalide.");
    expect(screen.getByLabelText("Taux horaire")).toHaveValue(750);
  });

  test("an unreachable server is worded as such on a row action", async () => {
    const user = userEvent.setup();
    employeesApi.setHourlyRate.mockRejectedValue({ code: "ECONNABORTED" }); // axios timeout: no response
    render(<MemoryRouter><EmployeesPage /></MemoryRouter>);
    await typeRate(user, "750");
    await user.click(screen.getByTitle("Enregistrer le taux"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Le serveur est inaccessible.");
  });

  test("a failed deletion says why instead of leaving the row silently in place", async () => {
    const user = userEvent.setup();
    employeesApi.remove.mockRejectedValue({ response: { data: { detail: "Ce compte a des heures enregistrées." } } });
    render(<MemoryRouter><EmployeesPage /></MemoryRouter>);
    await user.click(await screen.findByLabelText("Supprimer"));
    await user.click(screen.getByRole("button", { name: "Confirmer" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Ce compte a des heures enregistrées.");
    expect(screen.getByText("Ouvrier 02")).toBeInTheDocument();
  });

  test("three taps in one tick send a single PATCH", async () => {
    employeesApi.setHourlyRate.mockResolvedValue({ data: {} });
    const user = userEvent.setup();
    render(<MemoryRouter><EmployeesPage /></MemoryRouter>);
    await typeRate(user, "750");
    const button = screen.getByTitle("Enregistrer le taux");
    button.click();
    button.click();
    button.click();
    await waitFor(() => expect(employeesApi.setHourlyRate).toHaveBeenCalledTimes(1));
  });
});
