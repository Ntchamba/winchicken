import { stockApi } from "./endpoints";
import { todayISO } from "../utils/localDate";

/**
 * Persist the stock item definitions *and* the Quantité column that comes with them.
 *
 * `PUT /stock-items/` deliberately ignores `quantity`: `StockItem` carries no on-hand field,
 * the level is derived from `StockMovement` rows. So whoever saves the form has to follow the
 * PUT with a movement per changed row, and a caller that forgets silently drops every quantity
 * the user typed — which is exactly what onboarding step 2 did until 2026-09-15, leaving a
 * freshly configured farm reading 0 of everything.
 *
 * The movement is the **difference** between what the user typed and the level as it stands
 * after the PUT: an IN when they raised it, an OUT when they lowered it, nothing when the row
 * is untouched. Posting the whole quantity (which is what this did while the PUT still deleted
 * and recreated every row) would double the stock on every save now that the upsert keeps the
 * movement history.
 *
 * This is the one place that knows the two-step shape. Both callers go through it.
 *
 * @param {number} farmId
 * @param {object[]} items - rows from `StockParametersForm`'s payload.
 * @param {{note: string}} options - French note recorded on each movement, naming the origin.
 * @returns {Promise<object>} the PUT response body (items with their `item_code`s).
 */
export async function saveStockItemsWithQuantities(farmId, items, { note }) {
  // 1. Persist the item definitions (upsert, keyed on item_code).
  const { data } = await stockApi.putItems(farmId, items);

  // 2. Move the stock to the level the user typed. Until FIX 3.5 the PUT deleted and recreated
  //    every StockItem, cascading its movements away, so this re-posted each row's *whole*
  //    quantity to rebuild the level from zero. The upsert keeps those movements, so re-posting
  //    the whole quantity now doubles the stock on every save — post the difference instead.
  //
  //    The base is the level the server reports *after* the upsert, not the form's load-time
  //    `original_quantity`: the screen stays open for hours, and what the user means by typing a
  //    number is "the level is this now", whatever moved in the meantime.
  const byName = {};
  for (const it of data.items || []) byName[it.name] = it;

  const movements = (items || [])
    .filter((it) => it.quantity != null && byName[it.name])
    .map((it) => {
      const current = Number(byName[it.name].current_quantity) || 0;
      const delta = Number(it.quantity) - current;
      if (!delta) return null;

      // Adding a brand-new article to stock is a purchase: file it in Finances at
      // quantity × unit price (the backend turns total_price into the Expense, under the
      // category the article's type implies). Re-saving an existing item's level sends
      // nothing → no double-count.
      const unitPrice = Number(byName[it.name].unit_price) || 0;
      const totalPrice = it.is_new_item && unitPrice > 0 ? delta * unitPrice : null;
      // Composed item whose level was raised here → treat the increase as a production run:
      // deduct the recipe ingredients scaled to the delta (backend, via production_quantity).
      const production = it.deduct_production && delta > 0 ? delta : null;
      return stockApi.addMovement({
        item: byName[it.name].item_code,
        movement_type: delta > 0 ? "IN" : "OUT",
        quantity: Math.abs(delta),
        movement_date: it.movement_date || todayISO(),
        note,
        ...(totalPrice && totalPrice > 0 ? { total_price: totalPrice } : {}),
        ...(production ? { production_quantity: production } : {}),
      });
    })
    .filter(Boolean);

  if (movements.length) await Promise.all(movements);
  return data;
}
