import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import CalendarPage from "../CalendarPage";
import { scheduleApi } from "../../../api/endpoints";

// 2026-09-25: the grid used to download every task of the month (4.4 MB at 50 houses). It now
// reads per-day counts + the pills a cell shows, and fetches a day's full list when opened.

vi.mock("../../../api/endpoints", () => ({ scheduleApi: { monthSummary: vi.fn(), day: vi.fn() } }));
vi.mock("../../../components/QuickLinksBar", () => ({ default: () => null }));

const now = new Date();
const key = (d) => `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
const pill = (id, what) => ({ id, startTime: null, houseName: "Salle 1", what, category: "Alimentation" });

describe("CalendarPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    scheduleApi.monthSummary.mockResolvedValue({
      data: {
        categories: ["Alimentation"],
        days: { [key(10)]: { count: 5, preview: [pill("a", "Aliment 1"), pill("b", "Aliment 2"), pill("c", "Aliment 3")] } },
      },
    });
    scheduleApi.day.mockResolvedValue({
      data: Array.from({ length: 5 }, (_, i) => ({ ...pill(`d${i}`, `Tâche complète ${i}`), batchName: "Bande A", details: "" })),
    });
  });

  test("a cell shows the preview pills and how many more there are", async () => {
    render(<MemoryRouter><CalendarPage /></MemoryRouter>);
    expect(await screen.findByText(/Aliment 3/)).toBeInTheDocument();
    expect(screen.getByText("+2")).toBeInTheDocument();
    expect(scheduleApi.monthSummary).toHaveBeenCalledTimes(1);
    expect(scheduleApi.day).not.toHaveBeenCalled();
  });

  test("opening a day fetches and lists all of its tasks", async () => {
    render(<MemoryRouter><CalendarPage /></MemoryRouter>);
    await userEvent.click((await screen.findByText(/Aliment 1/)).closest("button"));
    await waitFor(() => expect(scheduleApi.day).toHaveBeenCalledWith(key(10)));
    expect(await screen.findByText(/Tâche complète 4/)).toBeInTheDocument();
    expect(screen.getAllByText(/Tâche complète/)).toHaveLength(5);
  });

  test("a day that fails to load says so", async () => {
    scheduleApi.day.mockRejectedValue(new Error("réseau"));
    render(<MemoryRouter><CalendarPage /></MemoryRouter>);
    await userEvent.click((await screen.findByText(/Aliment 1/)).closest("button"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Les tâches de ce jour n'ont pas pu être chargées.");
  });
});
