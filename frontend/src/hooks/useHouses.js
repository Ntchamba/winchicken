import { useCallback, useEffect, useState } from "react";
import { batchesApi, housesApi } from "../api/endpoints";

// PoultryHouse has no productionType of its own (only PoultryBatch does) — the sidebar's
// Egg-vs-Bird icon is derived from each house's active batch, defaulting to Broiler for a
// house with no active batch yet.
const TYPE_LABELS = { BROILER: "Broiler", PULLET: "Pullet", LAYER: "Layer" };

/**
 * Single source of truth for "the farm's houses, each with its active batch's name/code"
 * (2026-08-25) — used by the sidebar (`DashboardLayout`, via `HousesContext`) and by anything
 * that needs to refresh it after a write (`ProtocolEditModal`, after renaming a batch or
 * editing its protocol). Exposes the standard `{data, loading, error, refetch}` shape rather
 * than ad hoc fetching duplicated per component — see docs/architecture.md.
 */
export default function useHouses() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    try {
      const [housesRes, batchesRes] = await Promise.all([housesApi.list(), batchesApi.listActive()]);
      const houseResults = housesRes.data.results || housesRes.data;
      const batchResults = batchesRes.data.results || batchesRes.data;
      const activeBatchByHouse = Object.fromEntries(
        batchResults.filter((b) => b.status === "ACTIVE").map((b) => [b.house_code, b])
      );
      setData(
        houseResults.map((h) => {
          const batch = activeBatchByHouse[h.house_code];
          return {
            houseCode: h.house_code,
            name: h.name,
            maxCapacity: h.max_capacity,
            type: TYPE_LABELS[batch?.production_type] || "Broiler",
            activeBatchName: batch?.name || "",
            activeBatchCode: batch?.batch_code || null,
          };
        })
      );
      setError(null);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { houses: data, loading, error, refetch };
}
