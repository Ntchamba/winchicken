import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import EmployeesPage from "../EmployeesPage";
import { employeesApi } from "../../../api/endpoints";

// Excel import for employees (docs/excel-import.md): update-or-create by email, and the
// summary must show the one-time temporary password for every newly-created account.

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

describe("EmployeesPage — Excel import", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    employeesApi.list.mockResolvedValue({ data: [] });
  });

  test("imports a file and shows the summary + temp-password list for new accounts", async () => {
    employeesApi.importXlsx.mockResolvedValue({
      data: {
        updated: 1,
        created: 1,
        skipped: [{ line: 5, reason: "rôle invalide : « Superviseur »." }],
        newAccounts: [{ line: 3, name: "Marie Dupont", email: "marie@example.com", password: "Tmp-abc123" }],
      },
    });

    const { container } = render(<MemoryRouter><EmployeesPage /></MemoryRouter>);
    await waitFor(() => expect(employeesApi.list).toHaveBeenCalled());

    await userEvent.upload(container.querySelector('input[type="file"]'), new File(["x"], "employes.xlsx"));

    await waitFor(() => expect(employeesApi.importXlsx).toHaveBeenCalledWith(expect.any(File)));
    expect(await screen.findByText(/1 ligne mise à jour, 1 ligne créée, 1 ligne ignorée/i)).toBeInTheDocument();
    expect(screen.getByText("Ligne 5 : rôle invalide : « Superviseur ».")).toBeInTheDocument();
    // the one-time temp password is displayed for the admin to hand off
    expect(screen.getByText("Tmp-abc123")).toBeInTheDocument();
    expect(screen.getByText(/marie@example.com/)).toBeInTheDocument();
    // list refetched after import
    expect(employeesApi.list).toHaveBeenCalledTimes(2);
  });

  test("a parse failure shows the server message", async () => {
    employeesApi.importXlsx.mockRejectedValue({
      isAxiosError: true,
      response: { data: { detail: "En-têtes de colonnes introuvables : « Email »." } },
    });
    const { container } = render(<MemoryRouter><EmployeesPage /></MemoryRouter>);
    await waitFor(() => expect(employeesApi.list).toHaveBeenCalled());
    await userEvent.upload(container.querySelector('input[type="file"]'), new File(["x"], "bad.xlsx"));
    expect(await screen.findByText(/En-têtes de colonnes introuvables/)).toBeInTheDocument();
  });
});
