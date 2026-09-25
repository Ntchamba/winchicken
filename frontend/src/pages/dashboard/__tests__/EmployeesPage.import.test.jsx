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
    importJob: vi.fn(),
    discardImportJob: vi.fn(),
    importTemplateUrl: "http://test/employees/import-template.xlsx",
  },
}));
vi.mock("../../../hooks/useDocumentTitle", () => ({ default: vi.fn() }));

const RESULT = {
  updated: 1,
  created: 1,
  skipped: [{ line: 5, reason: "rôle invalide : « Superviseur »." }],
  newAccounts: [{ line: 3, name: "Marie Dupont", email: "marie@example.com", password: "Tmp-abc123" }],
};

describe("EmployeesPage — Excel import", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    employeesApi.list.mockResolvedValue({ data: [] });
    employeesApi.importXlsx.mockResolvedValue({ data: { jobId: "job1", status: "queued", processed: 0, total: null } });
    employeesApi.discardImportJob.mockResolvedValue({});
  });

  test("imports a file and shows the summary + temp-password list for new accounts", async () => {
    employeesApi.importJob.mockResolvedValue({ data: { jobId: "job1", status: "done", processed: 2, total: 2, result: RESULT } });

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
    expect(employeesApi.importJob).toHaveBeenCalledWith("job1");
  });

  test("shows progress while the job runs, then the summary", async () => {
    employeesApi.importJob
      .mockResolvedValueOnce({ data: { jobId: "job1", status: "running", processed: 3, total: 10 } })
      .mockResolvedValue({ data: { jobId: "job1", status: "done", processed: 10, total: 10, result: RESULT } });
    const { container } = render(<MemoryRouter><EmployeesPage /></MemoryRouter>);
    await userEvent.upload(container.querySelector('input[type="file"]'), new File(["x"], "employes.xlsx"));
    expect(await screen.findByText(/Import en cours : 3 \/ 10 lignes/)).toBeInTheDocument();
    expect(await screen.findByText("Tmp-abc123", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.queryByText(/Import en cours/)).not.toBeInTheDocument();
  });

  test("coming back to the page resumes the job, and closing the summary forgets it", async () => {
    localStorage.setItem("winchicken_employee_import_job", "job9");
    employeesApi.importJob.mockResolvedValue({ data: { jobId: "job9", status: "done", processed: 2, total: 2, result: RESULT } });
    render(<MemoryRouter><EmployeesPage /></MemoryRouter>);
    expect(await screen.findByText("Tmp-abc123")).toBeInTheDocument();
    expect(employeesApi.importJob).toHaveBeenCalledWith("job9");

    await userEvent.click(screen.getByRole("button", { name: "Fermer ce résumé" }));
    expect(screen.queryByText("Tmp-abc123")).not.toBeInTheDocument();
    expect(employeesApi.discardImportJob).toHaveBeenCalledWith("job9");
    expect(localStorage.getItem("winchicken_employee_import_job")).toBeNull();
  });

  test("a job that fails says why", async () => {
    employeesApi.importJob.mockResolvedValue({
      data: { jobId: "job1", status: "error", detail: "L'import s'est interrompu. Les comptes déjà créés sont conservés." },
    });
    const { container } = render(<MemoryRouter><EmployeesPage /></MemoryRouter>);
    await userEvent.upload(container.querySelector('input[type="file"]'), new File(["x"], "employes.xlsx"));
    expect(await screen.findByText(/Les comptes déjà créés sont conservés/)).toBeInTheDocument();
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
