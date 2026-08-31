/**
 * Given the farm's stock compositions, map each output item_code to the first recipe that
 * produces it AND declares a usable base yield. Used by the Stock screens to decide whether
 * raising a composed item's stock should also deduct its ingredients ("comme une exécution").
 *
 * @param {{output_item: string, name: string, base_output_quantity: ?number}[]} compositions
 * @returns {Record<string, {name: string, baseYield: number}>}
 */
export function compositionByOutput(compositions = []) {
  const map = {};
  for (const c of compositions) {
    if (c.base_output_quantity > 0 && !map[c.output_item]) {
      map[c.output_item] = { name: c.name, baseYield: c.base_output_quantity };
    }
  }
  return map;
}
