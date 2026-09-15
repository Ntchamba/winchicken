import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import EmployeesPage from "../EmployeesPage";
import { employeesApi } from "../../../api/endpoints";

// FIX 6: one of ten worker creations was reported lost with no message of any kind. The form
// carried no in-flight state, no success confirmation, and no <form> (so the phone keyboard's
// "Go" key submitted nothing) — a save that worked and a save that never happened looked
// identical. These pin down the feedback, not a specific server bug.

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

const fill = async (user) => {
  await user.type(screen.getByLabelText("Nom"), "Ouvrier 05");
  await user.type(screen.getByLabelText("Email"), "ouvrier5@ferme.local");
  await user.type(screen.getByLabelText("Mot de passe"), "MotDePasse123!");
};

describe("EmployeesPage — worker creation feedback", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    employeesApi.list.mockResolvedValue({ data: [] });
  });

  test("confirms the account in French once it is created", async () => {
    const user = userEvent.setup();
    employeesApi.create.mockResolvedValue({ data: { id: 5 } });
    render(<MemoryRouter><EmployeesPage /></MemoryRouter>);
    await fill(user);
    await user.click(screen.getByRole("button", { name: /Ajouter un employé/ }));
    expect(await screen.findByText("Compte créé : Ouvrier 05 (ouvrier5@ferme.local).")).toBeInTheDocument();
    expect(employeesApi.create).toHaveBeenCalledTimes(1);
  });

  test("a rejected creation shows the server's message instead of nothing", async () => {
    const user = userEvent.setup();
    employeesApi.create.mockRejectedValue({ response: { data: { email: ["Un compte existe déjà avec cet email."] } } });
    render(<MemoryRouter><EmployeesPage /></MemoryRouter>);
    await fill(user);
    await user.click(screen.getByRole("button", { name: /Ajouter un employé/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Un compte existe déjà avec cet email.");
    expect(screen.queryByText(/Compte créé/)).not.toBeInTheDocument();
  });

  test("an unreachable server is worded as such, not as a validation problem", async () => {
    const user = userEvent.setup();
    employeesApi.create.mockRejectedValue({ code: "ECONNABORTED" }); // axios timeout: no response
    render(<MemoryRouter><EmployeesPage /></MemoryRouter>);
    await fill(user);
    await user.click(screen.getByRole("button", { name: /Ajouter un employé/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Le serveur est inaccessible.");
  });

  test("the button is disabled while the save is in flight, so a double tap sends one request", async () => {
    const user = userEvent.setup();
    let resolveCreate;
    employeesApi.create.mockReturnValue(new Promise((r) => { resolveCreate = r; }));
    render(<MemoryRouter><EmployeesPage /></MemoryRouter>);
    await fill(user);
    const button = screen.getByRole("button", { name: /Ajouter un employé/ });
    await user.click(button);
    const busy = await screen.findByRole("button", { name: /Enregistrement/ });
    expect(busy).toBeDisabled();
    await user.click(busy);
    expect(employeesApi.create).toHaveBeenCalledTimes(1);
    resolveCreate({ data: { id: 5 } });
    expect(await screen.findByText(/Compte créé/)).toBeInTheDocument();
  });

  test("a failed refresh after a successful create says so rather than hiding the new account", async () => {
    const user = userEvent.setup();
    employeesApi.create.mockResolvedValue({ data: { id: 5 } });
    employeesApi.list.mockResolvedValueOnce({ data: [] }).mockRejectedValueOnce({ response: { data: {} } });
    render(<MemoryRouter><EmployeesPage /></MemoryRouter>);
    await fill(user);
    await user.click(screen.getByRole("button", { name: /Ajouter un employé/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("La liste des employés n'a pas pu être rechargée.");
  });
});
