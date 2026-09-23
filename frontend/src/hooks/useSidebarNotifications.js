import { useCallback, useEffect, useState } from "react";
import { alertsApi, financeApi, stockApi } from "../api/endpoints";
import { countOpenIncidents } from "../api/incidents";

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
 * queries `IncidentsPanel.jsx` already makes (`?resolved=false` / `?status=OPEN`), through
 * `countOpenIncidents` (api/incidents.js) — the house hub's count uses the same helper.
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
    const [unreadRes, stockRes, openCases] = await Promise.all([
      alertsApi.unreadCount(), stockApi.lowCount(), countOpenIncidents(),
    ]);
    setUnreadCount(unreadRes.data.count);
    setStockLowCount(stockRes.data.count);
    setOpenCasesCount(openCases);

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
