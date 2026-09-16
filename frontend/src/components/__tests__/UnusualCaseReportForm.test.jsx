import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import UnusualCaseReportForm from "../UnusualCaseReportForm";
import { maintenanceApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";

// FIX 8, group 2. The submit had no catch: a rejected report left a form that had simply
// stopped spinning, and a successful one collapsed with nothing said. Both read as "it did not
// go through" — and the answer to that, for someone looking at a sick bird, is to report it
// again.

vi.mock("../../api/endpoints", () => ({ maintenanceApi: { addCase: vi.fn() } }));
vi.mock("../../context/AuthContext", () => ({ useAuth: vi.fn() }));

const describeCase = async (user) => {
  await user.type(
    screen.getByPlaceholderText(/Décrire l'observation/),
    "Trois poules léthargiques, crêtes pâles",
  );
};

describe("UnusualCaseReportForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuth.mockReturnValue({ user: { id: 3, role: "WORKER" } });
    maintenanceApi.addCase.mockResolvedValue({ data: { case_code: "UC-1" } });
  });

  test("confirms the report in French instead of just collapsing", async () => {
    const user = userEvent.setup();
    const onReported = vi.fn();
    render(<UnusualCaseReportForm batchCode="BATCH-1" startOpen onReported={onReported} />);
    await describeCase(user);
    await user.click(screen.getByRole("button", { name: "Signaler" }));
    expect(await screen.findByText("Cas signalé. Il apparaît dans « Cas signalés ».")).toBeInTheDocument();
    expect(onReported).toHaveBeenCalled();
    expect(maintenanceApi.addCase).toHaveBeenCalledTimes(1);
  });

  test("a rejected report shows the server's message and keeps the description", async () => {
    const user = userEvent.setup();
    maintenanceApi.addCase.mockRejectedValue({ response: { data: { detail: "Bande clôturée." } } });
    render(<UnusualCaseReportForm batchCode="BATCH-1" startOpen />);
    await describeCase(user);
    await user.click(screen.getByRole("button", { name: "Signaler" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bande clôturée.");
    expect(screen.getByPlaceholderText(/Décrire l'observation/)).toHaveValue(
      "Trois poules léthargiques, crêtes pâles",
    );
    expect(screen.queryByText(/Cas signalé/)).not.toBeInTheDocument();
  });

  test("an unreachable server is worded as such, not as a validation problem", async () => {
    const user = userEvent.setup();
    maintenanceApi.addCase.mockRejectedValue({ code: "ECONNABORTED" }); // axios timeout: no response
    render(<UnusualCaseReportForm batchCode="BATCH-1" startOpen />);
    await describeCase(user);
    await user.click(screen.getByRole("button", { name: "Signaler" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Le serveur est inaccessible.");
  });

  test("a second submit during a slow save does not file the case twice", async () => {
    const user = userEvent.setup();
    let release;
    maintenanceApi.addCase.mockReturnValue(new Promise((resolve) => { release = () => resolve({ data: {} }); }));
    render(<UnusualCaseReportForm batchCode="BATCH-1" startOpen />);
    await describeCase(user);
    const form = screen.getByPlaceholderText(/Décrire l'observation/).closest("form");
    await user.click(screen.getByRole("button", { name: "Signaler" }));
    form.requestSubmit();
    await waitFor(() => expect(maintenanceApi.addCase).toHaveBeenCalledTimes(1));
    release();
  });
});
