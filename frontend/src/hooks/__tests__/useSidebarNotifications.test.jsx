import { renderHook, waitFor, act } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

const api = vi.hoisted(() => ({
  unread: vi.fn(), low: vi.fn(), pending: vi.fn(), incidents: vi.fn(),
}));
vi.mock("../../api/endpoints", () => ({
  alertsApi: { unreadCount: () => api.unread() },
  stockApi: { lowCount: () => api.low() },
  financeApi: { pendingPayablesCount: () => api.pending() },
}));
vi.mock("../../api/incidents", () => ({ countOpenIncidents: () => api.incidents() }));

import useSidebarNotifications from "../useSidebarNotifications";

describe("useSidebarNotifications", () => {
  beforeEach(() => {
    api.unread.mockResolvedValue({ data: { count: 3 } });
    api.low.mockResolvedValue({ data: { count: 1 } });
    api.pending.mockResolvedValue({ data: { count: 4 } });
    api.incidents.mockResolvedValue(2);
    api.pending.mockClear();
  });

  test("loads every badge count for a role that may see payables", async () => {
    const { result } = renderHook(() => useSidebarNotifications(true));
    await waitFor(() => expect(result.current.financePendingCount).toBe(4));
    expect(result.current).toMatchObject({ unreadCount: 3, stockLowCount: 1, openCasesCount: 2 });
  });

  test("never asks for payables for any other role, and shows 0", async () => {
    const { result } = renderHook(() => useSidebarNotifications(false));
    await waitFor(() => expect(result.current.openCasesCount).toBe(2));
    expect(result.current.financePendingCount).toBe(0);
    expect(api.pending).not.toHaveBeenCalled();
  });

  test("refetch picks up new counts", async () => {
    const { result } = renderHook(() => useSidebarNotifications(false));
    await waitFor(() => expect(result.current.unreadCount).toBe(3));
    api.unread.mockResolvedValue({ data: { count: 0 } });
    api.incidents.mockResolvedValue(0);
    await act(() => result.current.refetch());
    expect(result.current.unreadCount).toBe(0);
    expect(result.current.openCasesCount).toBe(0);
  });
});
