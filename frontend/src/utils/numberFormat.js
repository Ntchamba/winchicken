// French number display: decimal comma, space-grouped thousands, trailing zeros dropped.
// `"10.00"` (a DRF decimal) → `"10"`, `7.5` → `"7,5"`, `1234.5` → `"1 234,5"`. Money has its own
// formatter (utils/money.js), which always shows the unit.

/** Nullish / non-numeric input returns "—". */
export function formatNumber(value, maxDecimals = 2) {
  const n = Number(value);
  if (value == null || value === "" || Number.isNaN(n)) return "—";
  return n.toLocaleString("fr-FR", { maximumFractionDigits: maxDecimals });
}
