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

// Campaign 3: the Excel onboarding path creates articles *after* the page mounted, so the review
// form showed "Aucun article de stock consommé" on imported rows that did consume stock. A new
// refresh key reloads the list.
describe("useStockItemOptions — refresh", () => {
  test("a new refresh key reloads the articles", async () => {
    api.items.mockReset();
    api.items
      .mockResolvedValueOnce({ data: { items: [] } })
      .mockResolvedValueOnce({ data: { items: [{ item_code: "FEE-2-001", name: "Provende démarrage", unit: "kg" }] } });
    const { result, rerender } = renderHook(({ step }) => useStockItemOptions(2, step), { initialProps: { step: "excel" } });
    await waitFor(() => expect(api.items).toHaveBeenCalledTimes(1));
    rerender({ step: "manual" });
    await waitFor(() => expect(result.current).toEqual([{ item_code: "FEE-2-001", name: "Provende démarrage", unit: "kg" }]));
  });
});
