import { describe, expect, test, vi } from "vitest";

vi.mock("../localDate", () => ({ todayISO: () => "2026-09-24" }));

import { buildStockRows } from "../stockRows";

const item = (over = {}) => ({
  item_code: "FEE-1", name: "Aliment démarrage", category: 1, feed_stage: "GROWER",
  cold_chain_required: false, alert_threshold: 50, unit: "kg", unit_price: "350.00",
  supplier: "SPC", item_type: "", current_quantity: 120, ...over,
});

describe("buildStockRows", () => {
  test("groups rows under their category, every known category present even when empty", () => {
    const rows = buildStockRows([item()], [{ id: 1 }, { id: 2 }]);
    expect(Object.keys(rows)).toEqual(["1", "2"]);
    expect(rows[2]).toEqual([]);
    expect(rows[1][0]).toMatchObject({
      itemCode: "FEE-1", item: "Aliment démarrage", feedStage: "GROWER", threshold: 50,
      unit: "kg", price: "350.00", supplier: "SPC", date: "2026-09-24",
    });
  });

  test("an item of an unknown category still gets a group rather than being dropped", () => {
    const rows = buildStockRows([item({ category: 9 })], [{ id: 1 }]);
    expect(rows[9]).toHaveLength(1);
  });

  // The quantity is what a full-replace save re-posts; a lost quantity once zeroed a farm's stock.
  test("quantity and originalQuantity survive, zero included", () => {
    expect(buildStockRows([item({ current_quantity: 120 })], [{ id: 1 }])[1][0]).toMatchObject({ quantity: 120, originalQuantity: 120 });
    expect(buildStockRows([item({ current_quantity: 0 })], [{ id: 1 }])[1][0]).toMatchObject({ quantity: 0, originalQuantity: 0 });
  });

  test("an item with no level yet has a blank quantity but an original of 0", () => {
    const row = buildStockRows([item({ current_quantity: null })], [{ id: 1 }])[1][0];
    expect(row.quantity).toBe("");
    expect(row.originalQuantity).toBe(0);
  });

  test("defaults: starter feed stage, no cold chain, no supplier, no type", () => {
    const row = buildStockRows(
      [item({ feed_stage: null, cold_chain_required: null, supplier: undefined, item_type: null })], [{ id: 1 }],
    )[1][0];
    expect(row).toMatchObject({ feedStage: "STARTER", coldChain: false, supplier: null, itemType: "" });
  });

  test("row ids are unique across calls", () => {
    const a = buildStockRows([item()], [{ id: 1 }])[1][0].id;
    const b = buildStockRows([item()], [{ id: 1 }])[1][0].id;
    expect(a).not.toBe(b);
  });
});
