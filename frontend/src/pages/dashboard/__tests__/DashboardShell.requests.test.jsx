import React from "react";
import { act, render, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import DashboardShell from "../DashboardShell";
import { alertsApi, batchesApi, financeApi, housesApi, stockApi } from "../../../api/endpoints";

// Live QA 2026-09-25: every page load sent each sidebar request twice (the hooks' own mount fetch
// plus the shell's route-change effect firing on the first render too). Once per load, and once
// more per navigation — the refresh-on-navigation stays, a phone left on one screen needs it.

vi.mock("../../../api/endpoints", () => ({
  alertsApi: { unreadCount: vi.fn() },
  stockApi: { lowCount: vi.fn() },
  financeApi: { pendingPayablesCount: vi.fn() },
  maintenanceApi: { cases: vi.fn(() => Promise.resolve({ data: { count: 0, results: [] } })), faults: vi.fn(() => Promise.resolve({ data: { count: 0, results: [] } })) },
  housesApi: { list: vi.fn() },
  batchesApi: { listActive: vi.fn() },
}));
vi.mock("../../../context/AuthContext", () => ({
  useAuth: () => ({ user: { id: 1, name: "Admin", role: "ADMIN" }, logout: vi.fn() }),
}));
vi.mock("../../../components/DashboardLayout", () => ({ default: ({ children }) => <div>{children}</div> }));

let go;
function Page() {
  go = useNavigate();
  return null;
}

describe("DashboardShell sidebar requests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    alertsApi.unreadCount.mockResolvedValue({ data: { count: 0 } });
    stockApi.lowCount.mockResolvedValue({ data: { count: 0 } });
    financeApi.pendingPayablesCount.mockResolvedValue({ data: { count: 0 } });
    housesApi.list.mockResolvedValue({ data: [] });
    batchesApi.listActive.mockResolvedValue({ data: [] });
  });

  test("one of each per page load, one more per navigation", async () => {
    render(
      <MemoryRouter initialEntries={["/dashboard"]}>
        <Routes>
          <Route path="/dashboard" element={<DashboardShell />}>
            <Route index element={<Page />} />
            <Route path="stock" element={<Page />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => expect(financeApi.pendingPayablesCount).toHaveBeenCalled());
    for (const fn of [alertsApi.unreadCount, stockApi.lowCount, financeApi.pendingPayablesCount, housesApi.list]) {
      expect(fn).toHaveBeenCalledTimes(1);
    }

    await act(async () => { go("/dashboard/stock"); });
    await waitFor(() => expect(financeApi.pendingPayablesCount).toHaveBeenCalledTimes(2));
    expect(alertsApi.unreadCount).toHaveBeenCalledTimes(2);
    expect(housesApi.list).toHaveBeenCalledTimes(2);
  });
});
