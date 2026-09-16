import React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import MyTasksPage from "../MyTasksPage";
import { tasksApi } from "../../../api/endpoints";
import { useAuth } from "../../../context/AuthContext";

// FIX 7 — the same occurrence now appears in every assignee's "Mes tâches". Two things must be
// true on a shared row: the worker sees who else is on it (otherwise both do the round), and a
// row completed by one of them reads as done, with the completer's name, for all of them.

vi.mock("../../../api/endpoints", () => ({
  tasksApi: { mine: vi.fn(), complete: vi.fn(), uncomplete: vi.fn() },
}));
vi.mock("../../../context/AuthContext", () => ({ useAuth: vi.fn() }));
vi.mock("../../../components/QuickLinksBar", () => ({ default: () => null }));

const TASK = {
  id: "12", category: "Alimentation", icon: "wheat", what: "Aliment croissance",
  details: "55 kg", periodDay: 3, periodLength: 15, recurrence: null,
  houseCode: "H-1-001", houseName: "Bâtiment 1", timeSlotId: null, startTime: null, endTime: null,
  completable: true, done: false, completedAt: null, completedByName: null,
  assignedTo: [7, 8, 9], assignedToNames: ["Ouvrier 01", "Ouvrier 02", "Ouvrier 03"],
};

describe("MyTasksPage — a task shared by several workers", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuth.mockReturnValue({ user: { id: 7, name: "Ouvrier 01", role: "WORKER" } });
  });

  test("names the other assignees, and never the worker themselves", async () => {
    tasksApi.mine.mockResolvedValue({ data: [TASK] });
    render(<MyTasksPage />);
    expect(await screen.findByText("Partagée avec Ouvrier 02, Ouvrier 03")).toBeInTheDocument();
    expect(screen.queryByText(/Partagée avec.*Ouvrier 01/)).not.toBeInTheDocument();
  });

  test("a task with one assignee says nothing about sharing", async () => {
    tasksApi.mine.mockResolvedValue({
      data: [{ ...TASK, assignedTo: [7], assignedToNames: ["Ouvrier 01"] }],
    });
    render(<MyTasksPage />);
    await screen.findByText(/Aliment croissance/);
    expect(screen.queryByText(/Partagée avec/)).not.toBeInTheDocument();
  });

  test("a colleague's completion shows as done, with their name, in this worker's list", async () => {
    tasksApi.mine.mockResolvedValue({
      data: [{ ...TASK, done: true, completedByName: "Ouvrier 02" }],
    });
    render(<MyTasksPage />);
    expect(await screen.findByText(/Fait/)).toBeInTheDocument();
    expect(screen.getByText(/Ouvrier 02/, { selector: ".task-done-badge" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Marquer comme fait/ })).not.toBeInTheDocument();
  });
});
