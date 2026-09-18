import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import CashierPage from "../CashierPage";
import { financeApi } from "../../../api/endpoints";
import { todayISO } from "../../../utils/localDate";

// 2026-09-18 mobile audit, finding (3). `@media(max-width:767px)` hid `.data-table` column 4 on
// every table — "Total" here, the line total of a sale. A cashier on a phone saw the quantity
// and the unit price and not what the sale came to, with nothing saying a column was missing.
//
// Below 768px the table is now one card per row, and each cell carries its own header in
// `data-label` — that attribute *is* the column header on a phone, so a cell without one is the
// same bug in a new shape. jsdom applies no media queries, so what is pinned here is the
// invariant the CSS depends on; the rendered result is checked live by tools/responsive-audit.

vi.mock("../../../api/endpoints", () => ({
  financeApi: { sales: vi.fn(), addSale: vi.fn(), addExpense: vi.fn() },
}));
vi.mock("../../../hooks/useDocumentTitle", () => ({ default: vi.fn() }));
vi.mock("../../../components/QuickLinksBar", () => ({ default: () => null }));
vi.mock("../../../context/AuthContext", () => ({
  useAuth: () => ({ user: { id: 1, name: "Caissier", role: "CASHIER", farm: { name: "Ferme" } } }),
}));

// The page shows today's sales only, on the farm's own day — not the UTC one.
const TODAY = todayISO();
const SALES = [
  { id: 1, sale_date: TODAY, product_type: "POULTRY", quantity: 12, unit_price: 2500, total_amount: 30000, customer: "Marché central" },
  { id: 2, sale_date: TODAY, product_type: "EGGS", quantity: 30, unit_price: 100, total_amount: 3000, customer: null },
];

describe("CashierPage — Ventes du jour on a phone", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    financeApi.sales.mockResolvedValue({ data: SALES });
  });

  test("every column keeps its header on each row, so none can be dropped silently", async () => {
    render(<CashierPage />);
    expect(await screen.findByText("Marché central")).toBeInTheDocument();

    const table = document.querySelector("table.data-table");
    expect(table.className).toContain("stacked");

    const headers = Array.from(table.tHead.rows[0].cells).map((th) => th.textContent.trim());
    expect(headers).toEqual(["Produit", "Qté", "Prix unitaire", "Total", "Client", ""]);

    for (const row of table.tBodies[0].rows) {
      Array.from(row.cells).forEach((cell, index) => {
        const header = headers[index];
        if (!header) return; // the actions cell has no header of its own
        expect(cell.getAttribute("data-label")).toBe(header);
      });
    }
  });

  test("the line total is present and labelled — the column the old rule deleted", async () => {
    render(<CashierPage />);
    expect(await screen.findByText("Marché central")).toBeInTheDocument();

    const totals = Array.from(document.querySelectorAll('td[data-label="Total"]'));
    expect(totals.map((td) => td.textContent)).toEqual(["30000", "3000"]);
  });

  test("the day's total is labelled too, since its own label cell collapses on a phone", async () => {
    render(<CashierPage />);
    expect(await screen.findByText("Marché central")).toBeInTheDocument();

    const footer = document.querySelector('tfoot td[data-label="Total du jour"]');
    expect(footer).not.toBeNull();
    // formatMoney groups with a narrow no-break space (utils/money.js), not a plain one.
    expect(footer.textContent).toBe("33\u202f000 FCFA");
  });
});
