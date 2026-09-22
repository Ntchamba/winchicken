import { useCallback, useEffect, useState } from "react";
import { alertsApi, financeApi, maintenanceApi, stockApi } from "../api/endpoints";

// Reads either a paginated envelope's `count` or a plain array's `length` — the same
// `data.results || data` uncertainty every other list consumer in this app already handles,
// just reduced to a number instead of an array.
function countOf(data) {
  return typeof data.count === "number" ? data.count : (data.results || data).length;
}

/**
 * Sidebar bell/badge counts (2026-08-26): unread alert count (notification bell badge),
 * low-stock item count (Stock link badge), pending-payables count (Finance link badge,
 * Admin/Farm Manager only). `refetch` is meant to be called from the same trigger
 * `useHouses`/`HousesContext` already uses (DashboardShellContent's route-change effect) rather
 * than adding a second, independent polling mechanism.
 *
 * `openCasesCount` (2026-08-27, Part B pulse treatment) — no dedicated backend count endpoint
 * for this exists (unlike the other three, which each have their own `.../count/` view); rather
 * than add one for a frontend-scoped task, this sums the same two farm-wide, unresolved-only
 * queries `IncidentsPanel.jsx` already makes (`?resolved=false` / `?status=OPEN`) so the sidebar
 * badge always agrees with "Cas signalés" itself, no separate backend endpoint required.
 *
 * @param {boolean} canSeeFinancePendingCount - Only Admin/Farm Manager can call
 *   /purchase-orders/pending-count/ (403 otherwise, mirroring FinanceSummaryView's access
 *   split) — skipped entirely for other roles rather than firing the request and discarding a
 *   403, matching FinancePage.jsx's existing `summary.access !== "full"` pattern.
 */
export default function useSidebarNotifications(canSeeFinancePendingCount) {
  const [unreadCount, setUnreadCount] = useState(0);
  const [stockLowCount, setStockLowCount] = useState(0);
  const [financePendingCount, setFinancePendingCount] = useState(0);
  const [openCasesCount, setOpenCasesCount] = useState(0);

  const refetch = useCallback(async () => {
    const [unreadRes, stockRes, casesRes, faultsRes] = await Promise.all([
      alertsApi.unreadCount(), stockApi.lowCount(),
      maintenanceApi.cases({ resolved: "false" }), maintenanceApi.faults({ status: "OPEN" }),
    ]);
    setUnreadCount(unreadRes.data.count);
    setStockLowCount(stockRes.data.count);
    setOpenCasesCount(countOf(casesRes.data) + countOf(faultsRes.data));

    if (canSeeFinancePendingCount) {
      const financeRes = await financeApi.pendingPayablesCount();
      setFinancePendingCount(financeRes.data.count);
    } else {
      setFinancePendingCount(0);
    }
  }, [canSeeFinancePendingCount]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { unreadCount, stockLowCount, financePendingCount, openCasesCount, refetch };
}
