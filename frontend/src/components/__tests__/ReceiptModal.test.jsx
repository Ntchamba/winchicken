import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

// The printed sale receipt is the one document that leaves the farm. Campaign 3 found it showing
// "2026-09-24", "2500.00" and "75000.00" — ISO date and raw decimals, no currency.
vi.mock("../../context/AuthContext", () => ({ useAuth: () => ({ user: { farm_name: "Ferme Test" } }) }));

import ReceiptModal from "../ReceiptModal";

describe("ReceiptModal", () => {
  test("French date and FCFA amounts", () => {
    render(<ReceiptModal sale={{ id: 1, product_type: "EGG", quantity: 30, unit_price: "2500.00", total_amount: "75000.00", sale_date: "2026-09-24", customer: "Marché" }} onClose={() => {}} />);
    expect(screen.getByText("24/09/2026")).toBeInTheDocument();
    expect(screen.getByText("2 500 FCFA")).toBeInTheDocument();
    expect(screen.getByText("75 000 FCFA")).toBeInTheDocument();
  });
});
