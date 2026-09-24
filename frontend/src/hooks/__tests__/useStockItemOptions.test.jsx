import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

// The onboarding and full-page protocol screens gave the Consommation selector no articles, so
// after a reload it offered "Créer « Provende »" for an article the farm had (campaign 3).
const api = vi.hoisted(() => ({ items: vi.fn() }));
vi.mock("../../api/endpoints", () => ({ stockApi: { items: (...a) => api.items(...a) } }));

import useStockItemOptions from "../useStockItemOptions";

describe("useStockItemOptions", () => {
  test("loads the farm's articles in the selector's shape", async () => {
    api.items.mockResolvedValue({ data: { items: [{ item_code: "FEE-1-001", name: "Provende", unit: "kg", current_quantity: 3 }] } });
    const { result } = renderHook(() => useStockItemOptions(1));
    await waitFor(() => expect(result.current).toEqual([{ item_code: "FEE-1-001", name: "Provende", unit: "kg" }]));
    expect(api.items).toHaveBeenCalledWith(1);
  });

  test("no farm yet: nothing requested, an empty list", () => {
    api.items.mockClear();
    const { result } = renderHook(() => useStockItemOptions(undefined));
    expect(result.current).toEqual([]);
    expect(api.items).not.toHaveBeenCalled();
  });
});
