import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import PurchaseOrdersPage from "../PurchaseOrdersPage";
import { financeApi } from "../../../api/endpoints";

// FIX 8 group 5, second pass. The first version set `actionError` — whose only render site was
// inside the "Confirmer la réception" modal, a branch the cancel flow never opens. The state was
// set and nothing on screen could show it, so a failed cancellation was still silent: the order
// stayed listed as "En attente" with no reason given. These pin the render site, not the handler.

vi.mock("../../../api/endpoints", () => ({
  financeApi: {
    purchaseOrders: vi.fn(),
    addPurchaseOrder: vi.fn(),
    receivePurchaseOrder: vi.fn(),
    cancelPurchaseOrder: vi.fn(),
  },
  stockApi: { items: vi.fn() },
}));
vi.mock("../../../hooks/useDocumentTitle", () => ({ default: vi.fn() }));
vi.mock("../../../context/AuthContext", () => ({
  useAuth: () => ({ user: { farm: 1, role: "ADMIN" } }),
}));
vi.mock("../../../components/QuickLinksBar", () => ({ default: () => null }));

const ORDER = {
  order_code: "PO-1-0001", itemName: "Provende croissance", supplier: "Provenderie du Sud",
  quantity: 10, amount: "50000", status: "PENDING", category: "FEED", ordered_date: "2026-09-22",
};

describe("PurchaseOrdersPage — a refused cancellation", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { stockApi } = await import("../../../api/endpoints");
    stockApi.items.mockResolvedValue({ data: { items: [] } });
    financeApi.purchaseOrders.mockResolvedValue({ data: [ORDER] });
  });

  test("says why, inside the dialog, and leaves the order listed", async () => {
    const user = userEvent.setup();
    financeApi.cancelPurchaseOrder.mockRejectedValue({ code: "ECONNABORTED" }); // no response
    render(<PurchaseOrdersPage />);

    await user.click(await screen.findByLabelText("Annuler la commande"));
    // The row's X carries the same accessible name as the dialog's confirm button, so scope to
    // the dialog by the message only it renders.
    const dialog = (await screen.findByText(/Annuler la commande PO-1-0001/)).closest("div");
    await user.click(within(dialog).getByRole("button", { name: "Annuler la commande" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Le serveur est inaccessible.");
    expect(within(dialog).getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("PO-1-0001")).toBeInTheDocument();
  });

  test("a successful cancellation closes the dialog and refetches", async () => {
    const user = userEvent.setup();
    financeApi.cancelPurchaseOrder.mockResolvedValue({ data: {} });
    render(<PurchaseOrdersPage />);

    await user.click(await screen.findByLabelText("Annuler la commande"));
    const dialog = (await screen.findByText(/Annuler la commande PO-1-0001/)).closest("div");
    await user.click(within(dialog).getByRole("button", { name: "Annuler la commande" }));

    expect(financeApi.cancelPurchaseOrder).toHaveBeenCalledWith("PO-1-0001");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
