import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import AssignmentsPanel from "../AssignmentsPanel";
import { housesApi, tasksApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";

// FIX 4: an assignment on a task that is not due today used to be invisible — TasksNowPanel only
// renders what `compute_tasks_now` emits. These pin down the two things that made it a bug: the
// not-due row must still be listed (and marked as such), and it must still be clearable.
//
// FIX 7: a line carries several assignees, and this card is the only screen that can add one to
// a task that is not due today — so the picker has to work here too, sending the whole set.

vi.mock("../../api/endpoints", () => ({
  housesApi: { assignments: vi.fn(), assignTask: vi.fn() },
  tasksApi: { assignableUsers: vi.fn() },
}));

vi.mock("../../context/AuthContext", () => ({ useAuth: vi.fn() }));

const ROWS = [
  {
    id: "weighing-BATCH-A-1", what: "Peser un échantillon de la bande", category: "Pesée",
    assignedTo: [7], assignedToNames: ["Ouvrier 01"], activeToday: false, periodLabel: "Hebdomadaire",
  },
  {
    id: "12", what: "Aliment démarrage", category: "Alimentation",
    assignedTo: [7, 8], assignedToNames: ["Ouvrier 01", "Ouvrier 02"], activeToday: true,
    periodLabel: "Jours 1 à 15",
  },
];

const USERS = [
  { id: 7, name: "Ouvrier 01", role: "WORKER" },
  { id: 8, name: "Ouvrier 02", role: "WORKER" },
  { id: 9, name: "Ouvrier 03", role: "WORKER" },
];

describe("AssignmentsPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuth.mockReturnValue({ user: { id: 1, role: "ADMIN" } });
    housesApi.assignments.mockResolvedValue({ data: ROWS });
    housesApi.assignTask.mockResolvedValue({ data: { assignedTo: [], assignedToNames: [] } });
    tasksApi.assignableUsers.mockResolvedValue({ data: USERS });
  });

  test("lists an assignment whose task is not due today, marked as such", async () => {
    render(<AssignmentsPanel houseCode="H-1-001" />);
    expect(await screen.findByText(/Peser un échantillon de la bande/)).toBeInTheDocument();
    expect(screen.getByText(/Pas prévue aujourd'hui — Hebdomadaire/)).toBeInTheDocument();
    expect(screen.getByText(/Prévue aujourd'hui — Jours 1 à 15/)).toBeInTheDocument();
  });

  test("shows every assignee of a line, not just the first", async () => {
    render(<AssignmentsPanel houseCode="H-1-001" />);
    expect(await screen.findByText("Assignée à Ouvrier 01, Ouvrier 02")).toBeInTheDocument();
  });

  test("adding a second worker to a not-due task sends the whole set", async () => {
    render(<AssignmentsPanel houseCode="H-1-001" />);
    await userEvent.click((await screen.findAllByRole("button", { name: /Modifier/ }))[0]);
    await userEvent.click(await screen.findByRole("checkbox", { name: "Ouvrier 03" }));
    await waitFor(() =>
      expect(housesApi.assignTask).toHaveBeenCalledWith("H-1-001", "weighing-BATCH-A-1", [7, 9]),
    );
  });

  test("removing a not-due assignment clears it through the assign endpoint", async () => {
    const onChanged = vi.fn();
    render(<AssignmentsPanel houseCode="H-1-001" onChanged={onChanged} />);
    const rows = await screen.findAllByRole("button", { name: "Retirer" });
    await userEvent.click(rows[0]);
    await waitFor(() =>
      expect(housesApi.assignTask).toHaveBeenCalledWith("H-1-001", "weighing-BATCH-A-1", []),
    );
    expect(onChanged).toHaveBeenCalled();
    await waitFor(() =>
      expect(screen.queryByText(/Peser un échantillon de la bande/)).not.toBeInTheDocument(),
    );
  });

  test("a failed removal shows a French error instead of silently dropping the row", async () => {
    housesApi.assignTask.mockRejectedValue({ response: { status: 500, data: "" } });
    render(<AssignmentsPanel houseCode="H-1-001" />);
    await userEvent.click((await screen.findAllByRole("button", { name: "Retirer" }))[0]);
    expect(await screen.findByText(/Le retrait de l'affectation a échoué\. Le serveur a rencontré un problème/)).toBeInTheDocument();
    expect(screen.getByText(/Peser un échantillon de la bande/)).toBeInTheDocument();
  });

  test("a role without assignment rights renders nothing at all, heading included", async () => {
    useAuth.mockReturnValue({ user: { id: 7, role: "WORKER" } });
    const { container } = render(<AssignmentsPanel houseCode="H-1-001" />);
    expect(container).toBeEmptyDOMElement();
    expect(housesApi.assignments).not.toHaveBeenCalled();
  });
});
