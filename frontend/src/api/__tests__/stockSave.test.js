import { beforeEach, describe, expect, test, vi } from "vitest";

import { saveStockItemsWithQuantities } from "../stockSave";
import { stockApi } from "../endpoints";

// The stock PUT became an upsert in FIX 3.5, so it no longer deletes the movement history.
// This helper used to re-post each row's whole quantity to rebuild the level from zero — doing
// that now adds the level on top of itself, and a farmer who opens "Mettre à jour le stock" and
// saves without touching anything watches their stock double. It must post the difference.

vi.mock("../endpoints", () => ({
  stockApi: { putItems: vi.fn(), addMovement: vi.fn() },
}));

const putReturns = (items) => stockApi.putItems.mockResolvedValue({ data: { items } });

describe("saveStockItemsWithQuantities — the level movement", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    stockApi.addMovement.mockResolvedValue({ data: {} });
  });

  test("an unchanged row posts no movement at all", async () => {
    putReturns([{ item_code: "FEE-1-001", name: "Provende", current_quantity: 800, unit_price: 450 }]);
    await saveStockItemsWithQuantities(1, [{ name: "Provende", quantity: 800, original_quantity: 800 }], {
      note: "Saisie",
    });
    expect(stockApi.addMovement).not.toHaveBeenCalled();
  });

  test("raising the level posts an IN for the difference only", async () => {
    putReturns([{ item_code: "FEE-1-001", name: "Provende", current_quantity: 800, unit_price: 450 }]);
    await saveStockItemsWithQuantities(1, [{ name: "Provende", quantity: 950, original_quantity: 800 }], {
      note: "Saisie",
    });
    expect(stockApi.addMovement).toHaveBeenCalledTimes(1);
    expect(stockApi.addMovement).toHaveBeenCalledWith(
      expect.objectContaining({ item: "FEE-1-001", movement_type: "IN", quantity: 150 }),
    );
  });

  test("lowering the level posts an OUT for the difference", async () => {
    putReturns([{ item_code: "FEE-1-001", name: "Provende", current_quantity: 800, unit_price: 450 }]);
    await saveStockItemsWithQuantities(1, [{ name: "Provende", quantity: 620, original_quantity: 800 }], {
      note: "Saisie",
    });
    expect(stockApi.addMovement).toHaveBeenCalledWith(
      expect.objectContaining({ item: "FEE-1-001", movement_type: "OUT", quantity: 180 }),
    );
  });

  test("the base is the server's level after the PUT, not the form's load-time value", async () => {
    // The screen sat open while a task deducted 40 kg; the worker still means "it is 800 now".
    putReturns([{ item_code: "FEE-1-001", name: "Provende", current_quantity: 760, unit_price: 450 }]);
    await saveStockItemsWithQuantities(1, [{ name: "Provende", quantity: 800, original_quantity: 800 }], {
      note: "Saisie",
    });
    expect(stockApi.addMovement).toHaveBeenCalledWith(
      expect.objectContaining({ movement_type: "IN", quantity: 40 }),
    );
  });

  test("a brand-new article files its purchase at the delta × unit price", async () => {
    putReturns([{ item_code: "FEE-1-002", name: "Maïs", current_quantity: 0, unit_price: 300 }]);
    await saveStockItemsWithQuantities(
      1, [{ name: "Maïs", quantity: 200, original_quantity: 0, is_new_item: true }], { note: "Saisie" },
    );
    expect(stockApi.addMovement).toHaveBeenCalledWith(
      expect.objectContaining({ movement_type: "IN", quantity: 200, total_price: 60000 }),
    );
  });

  test("a composed item's production run is scaled to the increase", async () => {
    putReturns([{ item_code: "FEE-1-003", name: "Provende maison", current_quantity: 100, unit_price: 0 }]);
    await saveStockItemsWithQuantities(
      1, [{ name: "Provende maison", quantity: 180, original_quantity: 100, deduct_production: true }],
      { note: "Saisie" },
    );
    expect(stockApi.addMovement).toHaveBeenCalledWith(
      expect.objectContaining({ movement_type: "IN", quantity: 80, production_quantity: 80 }),
    );
  });

  test("a row left blank is ignored rather than zeroing the stock", async () => {
    putReturns([{ item_code: "FEE-1-001", name: "Provende", current_quantity: 800, unit_price: 450 }]);
    await saveStockItemsWithQuantities(1, [{ name: "Provende", quantity: null, original_quantity: 800 }], {
      note: "Saisie",
    });
    expect(stockApi.addMovement).not.toHaveBeenCalled();
  });
});
