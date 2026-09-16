import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import CashierPage from "../CashierPage";
import { financeApi } from "../../../api/endpoints";

// FIX 8, group 1. Both handlers here were `try {} finally {}` with no catch: a rejected save
// showed the cashier nothing at all, and the expense form's only feedback was a bare "Dépense
// enregistrée." that could not distinguish one entry from the next. A sale is money — "rien ne
// s'est passé" and "c'est enregistré" must never look the same.

vi.mock("../../../api/endpoints", () => ({
  financeApi: { sales: vi.fn(), addSale: vi.fn(), addExpense: vi.fn() },
}));
vi.mock("../../../hooks/useDocumentTitle", () => ({ default: vi.fn() }));
vi.mock("../../../components/QuickLinksBar", () => ({ default: () => null }));
// The page renders ReceiptModal, which reads the farm from AuthContext.
vi.mock("../../../context/AuthContext", () => ({
  useAuth: () => ({ user: { id: 1, name: "Caissier", role: "CASHIER", farm: { name: "Ferme" } } }),
}));

const fillSale = async (user) => {
  await user.type(screen.getByLabelText("Quantité"), "12");
  await user.type(screen.getByLabelText("Prix unitaire"), "2500");
};

describe("CashierPage — recording a sale", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    financeApi.sales.mockResolvedValue({ data: [] });
    financeApi.addSale.mockResolvedValue({ data: { id: 1 } });
    financeApi.addExpense.mockResolvedValue({ data: { id: 1 } });
  });

  test("confirms in French what was recorded, not just that something was", async () => {
    const user = userEvent.setup();
    render(<CashierPage />);
    await fillSale(user);
    await user.click(screen.getByRole("button", { name: /Enregistrer la vente/ }));
    expect(await screen.findByText("Vente enregistrée : Volaille — 30 000 FCFA.")).toBeInTheDocument();
    expect(financeApi.addSale).toHaveBeenCalledTimes(1);
  });

  test("a rejected sale shows the server's message and keeps what was typed", async () => {
    const user = userEvent.setup();
    financeApi.addSale.mockRejectedValue({ response: { data: { detail: "Bande introuvable." } } });
    render(<CashierPage />);
    await fillSale(user);
    await user.click(screen.getByRole("button", { name: /Enregistrer la vente/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Bande introuvable.");
    expect(screen.queryByText(/Vente enregistrée/)).not.toBeInTheDocument();
    // Re-typing a sale on a phone is how a sale gets recorded twice, or not at all.
    expect(screen.getByLabelText("Quantité")).toHaveValue(12);
    expect(screen.getByLabelText("Prix unitaire")).toHaveValue(2500);
  });

  test("an unreachable server is worded as such, not as a validation problem", async () => {
    const user = userEvent.setup();
    financeApi.addSale.mockRejectedValue({ code: "ECONNABORTED" }); // axios timeout: no response
    render(<CashierPage />);
    await fillSale(user);
    await user.click(screen.getByRole("button", { name: /Enregistrer la vente/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Le serveur est inaccessible.");
  });

  test("the phone keyboard's Go key submits the sale", async () => {
    const user = userEvent.setup();
    render(<CashierPage />);
    await fillSale(user);
    screen.getByLabelText("Quantité").closest("form").requestSubmit();
    await waitFor(() => expect(financeApi.addSale).toHaveBeenCalledTimes(1));
  });

  test("a second tap during a slow save does not record the sale twice", async () => {
    const user = userEvent.setup();
    let release;
    financeApi.addSale.mockReturnValue(new Promise((resolve) => { release = () => resolve({ data: {} }); }));
    render(<CashierPage />);
    await fillSale(user);
    const button = screen.getByRole("button", { name: /Enregistrer la vente/ });
    await user.click(button);
    expect(await screen.findByRole("button", { name: /Enregistrement…/ })).toBeDisabled();
    await user.click(button);
    expect(financeApi.addSale).toHaveBeenCalledTimes(1);
    release();
  });

  test("three clicks in one tick still record one sale — the guard is a ref, not state", async () => {
    // Found by the FIX 8 verification pass: `saving` is React state, so it only blocks a second
    // submit once the update has flushed. No human can click three times inside one tick, but
    // this is money, so the guard is synchronous.
    let release;
    financeApi.addSale.mockReturnValue(new Promise((resolve) => { release = () => resolve({ data: {} }); }));
    const user = userEvent.setup();
    render(<CashierPage />);
    await fillSale(user);
    const button = screen.getByRole("button", { name: /Enregistrer la vente/ });
    button.click();
    button.click();
    button.click();
    await waitFor(() => expect(financeApi.addSale).toHaveBeenCalledTimes(1));
    release();
  });

  test("an incomplete sale says what is missing instead of doing nothing", async () => {
    const user = userEvent.setup();
    render(<CashierPage />);
    await user.type(screen.getByLabelText("Quantité"), "12");
    await user.click(screen.getByRole("button", { name: /Enregistrer la vente/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Renseignez la quantité et le prix unitaire avant d'enregistrer.",
    );
    expect(financeApi.addSale).not.toHaveBeenCalled();
  });
});

describe("CashierPage — recording an expense", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    financeApi.sales.mockResolvedValue({ data: [] });
    financeApi.addExpense.mockResolvedValue({ data: { id: 1 } });
  });

  test("names the expense it recorded — nothing on this page lists them", async () => {
    const user = userEvent.setup();
    render(<CashierPage />);
    await user.type(screen.getByLabelText("Montant"), "45000");
    await user.click(screen.getByRole("button", { name: /Enregistrer la dépense/ }));
    expect(await screen.findByText("Dépense enregistrée : Aliment — 45 000 FCFA.")).toBeInTheDocument();
  });

  test("a rejected expense shows the server's message instead of nothing", async () => {
    const user = userEvent.setup();
    financeApi.addExpense.mockRejectedValue({ response: { data: { amount: ["Montant invalide."] } } });
    render(<CashierPage />);
    await user.type(screen.getByLabelText("Montant"), "45000");
    await user.click(screen.getByRole("button", { name: /Enregistrer la dépense/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Montant invalide.");
    expect(screen.queryByText(/Dépense enregistrée/)).not.toBeInTheDocument();
  });
});
