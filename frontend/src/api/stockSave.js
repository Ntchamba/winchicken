import { stockApi } from "./endpoints";
import { todayISO } from "../utils/localDate";

/**
 * Persist the stock item definitions *and* the Quantité column that comes with them.
 *
 * `PUT /stock-items/` deliberately ignores `quantity`: `StockItem` carries no on-hand field,
 * the level is derived from `StockMovement` rows. So whoever saves the form has to follow the
 * PUT with one IN movement per row, and a caller that forgets silently drops every quantity
 * the user typed — which is exactly what onboarding step 2 did until 2026-09-15, leaving a
 * freshly configured farm reading 0 of everything.
 *
 * This is the one place that knows the two-step shape. Both callers go through it.
 *
 * @param {number} farmId
 * @param {object[]} items - rows from `StockParametersForm`'s payload.
 * @param {{note: string}} options - French note recorded on each movement, naming the origin.
 * @returns {Promise<object>} the PUT response body (items with their fresh `item_code`s).
 */
export async function saveStockItemsWithQuantities(farmId, items, { note }) {
  // 1. Persist the item definitions (full replace).
  const { data } = await stockApi.putItems(farmId, items);

  // 2. The PUT recreated every StockItem (cascading away prior movements), so re-post each
  //    row's quantity against the fresh item_code, matched back by name.
  const byName = {};
  for (const it of data.items || []) byName[it.name] = it;

  const movements = (items || [])
    .filter((it) => it.quantity != null && Number(it.quantity) > 0 && byName[it.name])
    .map((it) => {
      // Adding a brand-new article to stock is a purchase: file it in Finances at
      // quantity × unit price (the backend turns total_price into the Expense, under the
      // category the article's type implies). Re-saving an existing item's stock level sends
      // nothing → no double-count.
      const unitPrice = Number(byName[it.name].unit_price) || 0;
      const totalPrice = it.is_new_item && unitPrice > 0 ? Number(it.quantity) * unitPrice : null;
      // Composed item whose level was raised here → treat the increase as a production run:
      // deduct the recipe ingredients scaled to the delta (backend, via production_quantity).
      const delta = Number(it.quantity) - (Number(it.original_quantity) || 0);
      const production = it.deduct_production && delta > 0 ? delta : null;
      return stockApi.addMovement({
        item: byName[it.name].item_code,
        movement_type: "IN",
        quantity: Number(it.quantity),
        movement_date: it.movement_date || todayISO(),
        note,
        ...(totalPrice && totalPrice > 0 ? { total_price: totalPrice } : {}),
        ...(production ? { production_quantity: production } : {}),
      });
    });

  if (movements.length) await Promise.all(movements);
  return data;
}
