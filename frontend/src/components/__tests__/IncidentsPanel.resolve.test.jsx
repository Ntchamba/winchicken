import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import IncidentsPanel from "../IncidentsPanel";
import { maintenanceApi } from "../../api/endpoints";

// FIX 8 group 5: "Résolu" was `try {} finally {}` with no catch. A WORKER/FARMER tapping it on
// an unusual case gets a 403 (UnusualCaseResolveView is Admin/Farm Manager only) — the card
// simply stayed in the open list, which reads as a tap that never registered. The panel's own
// list fetch had no catch either, so an API outage looked like a farm with no open cases.

vi.mock("../../api/endpoints", () => ({
  maintenanceApi: {
    cases: vi.fn(),
    faults: vi.fn(),
    resolveCase: vi.fn(),
    resolveFault: vi.fn(),
  },
}));

const CASE = {
  case_code: "UC-1-001", houseName: "Bat_1", batchName: "Bande 1",
  case_description: "Trois poules léthargiques", reporterName: "Ouvrier 02", case_date: "2026-09-20",
};

describe("IncidentsPanel — resolving a case", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    maintenanceApi.cases.mockResolvedValue({ data: [CASE] });
    maintenanceApi.faults.mockResolvedValue({ data: [] });
  });

  test("a refused resolve shows the server's reason and keeps the case listed", async () => {
    const user = userEvent.setup();
    maintenanceApi.resolveCase.mockRejectedValue({
      response: { status: 403, data: { detail: "Vous n'avez pas la permission d'effectuer cette action." } },
    });
    render(<IncidentsPanel houseCode="H-1-001" />);
    await user.click(await screen.findByRole("button", { name: /Résolu/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Vous n'avez pas la permission d'effectuer cette action.");
    expect(screen.getByText("Trois poules léthargiques")).toBeInTheDocument();
  });

  test("a failed list fetch says so instead of rendering an empty farm", async () => {
    maintenanceApi.cases.mockRejectedValue({ code: "ECONNABORTED" }); // axios timeout: no response
    render(<IncidentsPanel houseCode="H-1-001" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Le serveur est inaccessible.");
    expect(screen.queryByText("Aucun cas signalé ouvert.")).not.toBeInTheDocument();
  });

  test("a successful resolve refetches the list rather than leaving it stale", async () => {
    const user = userEvent.setup();
    maintenanceApi.resolveCase.mockResolvedValue({ data: {} });
    render(<IncidentsPanel houseCode="H-1-001" />);
    await user.click(await screen.findByRole("button", { name: /Résolu/ }));
    expect(maintenanceApi.resolveCase).toHaveBeenCalledWith("UC-1-001");
    expect(maintenanceApi.cases).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
