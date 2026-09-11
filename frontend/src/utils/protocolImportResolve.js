import { makeRow, nextRowId } from "./protocolRows";

/**
 * Turn a parsed Excel import payload into the form's `schedules` map, auto-creating the
 * categories and stock items the file names along the way.
 *
 * Extracted verbatim from HouseProtocolForm's `handleImportFile` (2026-09-11) so the
 * onboarding Excel-import screen resolves a file exactly the way the manual form does —
 * parsing/validation itself stays server-side and is untouched.
 *
 * @param {{rows: object[]}} data - The `protocolImportApi.parse` response body.
 * @param {object[]} categories - Current category list `[{ id, label }]`.
 * @param {object[]} stockItemList - Current stock items `[{ item_code, name }]`.
 * @param {?number} farmId - Missing farm id → resources are not auto-created (rows keep none).
 * @param {(label: string, icon: string) => Promise<{id: any}>} createCategory
 * @param {(name: string, categoryLabel: string, unit: string) => Promise<{item_code: string}>} createStockItem
 * @returns {Promise<{schedules: ?object, firstCategoryId: any}>} `schedules` is null when the
 *   file had no usable row — the caller must then leave the existing protocol untouched.
 */
export async function resolveProtocolImportRows(
  data,
  { categories, stockItemList, farmId, createCategory, createStockItem },
) {
  // 1. Resolve every distinct Catégorie to a category id, creating the missing ones.
  const labelToId = {};
  for (const c of categories) labelToId[c.label.trim().toLowerCase()] = c.id;
  for (const name of new Set(data.rows.map((r) => r.category))) {
    const key = name.trim().toLowerCase();
    if (labelToId[key] == null) labelToId[key] = (await createCategory(name, "Package")).id;
  }

  // 2. Resolve every distinct Consommation to a StockItem code, creating the missing ones.
  const nameToCode = {};
  for (const s of stockItemList) nameToCode[s.name.trim().toLowerCase()] = s.item_code;
  for (const r of data.rows) {
    if (!r.consumption) continue;
    const key = r.consumption.trim().toLowerCase();
    if (nameToCode[key] == null && farmId) {
      // Unité from the file is only used for a *new* resource; an existing one keeps its own.
      nameToCode[key] = (await createStockItem(r.consumption, r.category, r.unit)).item_code;
    }
  }

  // A file with no usable row must not silently wipe the whole protocol.
  if (data.rows.length === 0) return { schedules: null, firstCategoryId: null };

  const schedules = {};
  for (const r of data.rows) {
    const catId = labelToId[r.category.trim().toLowerCase()];
    if (catId == null) continue;
    const code = r.consumption ? nameToCode[r.consumption.trim().toLowerCase()] : null;
    (schedules[catId] ||= []).push(
      makeRow({
        fromValue: r.fromValue,
        toValue: r.untilEnd ? 1 : r.toValue,
        untilEnd: r.untilEnd,
        what: r.what,
        details: r.details || "",
        stockItemCode: code || null,
        consumptionMode: "fixed",
        quantityPerDay: code && r.quantityPerDay != null ? r.quantityPerDay : "",
        // Reuse the form's own time-slot shape ({ id, startTime, endTime }); the server
        // already dropped any malformed segment and reported it in `warnings`.
        timeSlots: (r.timeSlots || []).map((s) => ({ id: nextRowId(), startTime: s.startTime, endTime: s.endTime })),
      }),
    );
  }

  return { schedules, firstCategoryId: labelToId[data.rows[0].category.trim().toLowerCase()] ?? null };
}
