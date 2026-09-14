import { createContext, useContext } from "react";
import useHouses from "../hooks/useHouses";

const HousesContext = createContext(null);

/**
 * Provides one shared `useHouses()` instance to the whole `/dashboard/*` tree (2026-08-25) —
 * the sidebar (`DashboardLayout`) and the "Modifier" protocol-edit modal both read/refetch the
 * *same* houses list through this, instead of each page having to remember to call a
 * parent-supplied refresh callback after a save. This is the actual root-cause fix for the
 * sidebar-staleness bug: previously a save's `onSaved` callback had to be wired all the way up
 * to a refetch function threaded through outlet context by each page — easy to add correctly
 * once, easy to forget on the next new call site. `ProtocolEditModal` now calls
 * `useHousesContext().refetch()` itself, directly, regardless of what any given page's
 * `onSaved` does.
 */
export function HousesProvider({ children }) {
  const value = useHouses();
  return <HousesContext.Provider value={value}>{children}</HousesContext.Provider>;
}

export function useHousesContext() {
  const ctx = useContext(HousesContext);
  if (!ctx) throw new Error("useHousesContext must be used within a HousesProvider");
  return ctx;
}
