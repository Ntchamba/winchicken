import { todayISO } from "./localDate";

let rowId = 1;

/**
 * Flat `StockItemSerializer` list -> `{ [categoryId]: [row] }` for `StockParametersForm`.
 *
 * There is one mapper because there used to be two, and they disagreed: the onboarding copy
 * omitted `quantity` / `originalQuantity` / `date`. Saving that form does a full-replace PUT
 * that cascades away every StockMovement, and the quantities are restored from exactly these
 * fields — so a blank `quantity` meant the levels were destroyed and never re-posted. Going
 * through onboarding a second time zeroed the farm's whole stock.
 *
 * @param {object[]} items - `data.items` from `GET /farms/{id}/stock-items/`.
 * @param {object[]} categories
 */
export function buildStockRows(items, categories) {
  const map = Object.fromEntries(categories.map((c) => [c.id, []]));
  for (const item of items) {
    (map[item.category] ||= []).push({
      id: rowId++,
      itemCode: item.item_code,
      item: item.name,
      feedStage: item.feed_stage || "STARTER",
      coldChain: !!item.cold_chain_required,
      threshold: item.alert_threshold,
      unit: item.unit,
      price: item.unit_price,
      supplier: item.supplier ?? null,
      itemType: item.item_type || "",
      // The on-hand level, and the level as it was at load time so a composed item can tell an
      // increase from a re-save. Both must survive the round trip or the PUT loses them.
      quantity: item.current_quantity ?? "",
      originalQuantity: item.current_quantity ?? 0,
      date: todayISO(),
    });
  }
  return map;
}
