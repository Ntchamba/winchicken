// FCFA (XAF) is the farm's currency. Amounts used to print as bare numbers, which left
// "953 500" ambiguous next to counts like "954 volailles" — the unit is now always shown.
//
// Space-grouped thousands, no decimals: FCFA has no minor unit in practice, and prices in
// this app are whole numbers (feed at 450, birds at 2600).
export const CURRENCY = "FCFA";

/** `953500` → `"953 500 FCFA"`. Nullish/non-numeric input returns "—". */
export function formatMoney(amount, { currency = true } = {}) {
  const value = Number(amount);
  if (amount == null || Number.isNaN(value)) return "—";
  const formatted = Math.round(value).toLocaleString("fr-FR");
  return currency ? `${formatted} ${CURRENCY}` : formatted;
}
