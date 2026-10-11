import { formatMoney } from "./money";

/**
 * Plain-language verdict for the Finances hub's centre disc, from the same `cashOnHand` the
 * Trésorerie card shows (all-time sales − expenses − received orders, see
 * apps.finance.calculations.cash_on_hand) — one figure, so the disc and the card can never
 * disagree. Returns null for the restricted view, which never receives amounts.
 *
 * @param {object|null} summary - GET /finance/summary/ payload.
 * @returns {{label: string, detail: string, tier: "good"|"watch"|"critical"}|null}
 */
export function financeVerdict(summary) {
  if (summary?.access !== "full" || summary.cashOnHand == null) return null;
  const cash = Number(summary.cashOnHand);
  const detail = `Trésorerie : ${formatMoney(cash)}`;
  if (cash < 0) return { label: "Vous perdez de l'argent", detail, tier: "critical" };
  if (cash > 0) return { label: "Vous gagnez de l'argent", detail, tier: "good" };
  return { label: "Ni gain ni perte pour l'instant", detail, tier: "watch" };
}
