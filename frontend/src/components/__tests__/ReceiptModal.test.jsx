import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

// The printed sale receipt is the one document that leaves the farm. Campaign 3 found it showing
// "2026-09-24", "2500.00" and "75000.00" — ISO date and raw decimals, no currency.
vi.mock("../../context/AuthContext", () => ({ useAuth: () => ({ user: { farm_name: "Ferme Test" } }) }));

import ReceiptModal from "../ReceiptModal";

describe("ReceiptModal", () => {
  test("French date and FCFA amounts", () => {
    render(<ReceiptModal sale={{ id: 1, product_type: "EGG", quantity: 30, unit_price: "2500.00", total_amount: "75000.00", sale_date: "2026-09-24", customer: "Marché" }} onClose={() => {}} />);
    expect(screen.getAllByText("24/09/2026").length).toBeGreaterThan(0);
    // Rendered twice (screen + print area); \s because testing-library folds U+202F.
    expect(screen.getAllByText(/^2\s500 FCFA$/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/^75\s000 FCFA$/).length).toBeGreaterThan(0);
  });
});
