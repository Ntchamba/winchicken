import { renderHook, waitFor, act } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

// The sidebar's houses, each with its active batch. The batches come from ?status=ACTIVE, not
// from the first page of every batch: a layer flock started 18 months ago sits past row 20 of
// the newest-first list, and its house used to show as empty.

const api = vi.hoisted(() => ({ houses: vi.fn(), active: vi.fn(), all: vi.fn() }));
vi.mock("../../api/endpoints", () => ({
  housesApi: { list: () => api.houses() },
  batchesApi: { listActive: () => api.active(), list: () => api.all() },
}));

import useHouses from "../useHouses";

const page = (results) => ({ data: { count: results.length, results } });

describe("useHouses", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.houses.mockResolvedValue(page([
      { house_code: "H-1", name: "Pondeuses", max_capacity: 2000 },
      { house_code: "H-2", name: "Chair", max_capacity: 600 },
    ]));
    api.active.mockResolvedValue(page([
      { house_code: "H-1", status: "ACTIVE", production_type: "LAYER", name: "Ponte 2025", batch_code: "B-LAY" },
    ]));
    api.all.mockResolvedValue(page([]));
  });

  test("asks for the active batches only, so an old flock is never paged out", async () => {
    const { result } = renderHook(() => useHouses());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(api.active).toHaveBeenCalledTimes(1);
    expect(api.all).not.toHaveBeenCalled();
  });

  test("joins each house to its active batch; a house without one reads as Broiler and empty", async () => {
    const { result } = renderHook(() => useHouses());
    await waitFor(() => expect(result.current.houses).toHaveLength(2));
    expect(result.current.houses).toEqual([
      { houseCode: "H-1", name: "Pondeuses", maxCapacity: 2000, type: "Layer", activeBatchName: "Ponte 2025", activeBatchCode: "B-LAY" },
      { houseCode: "H-2", name: "Chair", maxCapacity: 600, type: "Broiler", activeBatchName: "", activeBatchCode: null },
    ]);
    expect(result.current.error).toBeNull();
  });

  test("a failed load keeps the error and stops loading; refetch recovers", async () => {
    api.houses.mockRejectedValueOnce(new Error("réseau"));
    const { result } = renderHook(() => useHouses());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBeInstanceOf(Error);
    await act(() => result.current.refetch());
    expect(result.current.error).toBeNull();
    expect(result.current.houses).toHaveLength(2);
  });
});
