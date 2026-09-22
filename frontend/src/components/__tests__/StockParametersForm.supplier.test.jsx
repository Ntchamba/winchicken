import { render, screen, waitFor, act, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";

import StockParametersForm from "../StockParametersForm";
import { stockApi } from "../../api/endpoints";

// FIX 8 group 4: the inline "nouveau fournisseur" field was `try {} finally {}` with no catch,
// so a rejected POST closed nothing, said nothing and left the row's supplier unset — and the
// empty-name case was a bare `return`, i.e. a dead button on a phone. It confirms on both
// Enter and the check button, so the in-flight guard has to be synchronous.

vi.mock("../../utils/localDate", () => ({
  todayISO: () => "2026-09-22",
  toLocalISODate: (v) => v,
}));

vi.mock("../../api/endpoints", () => ({
  stockApi: {
    categories: vi.fn(),
    items: vi.fn(),
    suppliers: vi.fn(),
    putItems: vi.fn(),
    addCategory: vi.fn(),
    deleteCategory: vi.fn(),
    removeCategory: vi.fn(),
    addSupplier: vi.fn(),
  },
}));

const CATEGORIES = [
  { id: 1, label: "Aliment", icon: "Wheat", kind: "FEED" },
  { id: 2, label: "Litière", icon: "Layers", kind: "OTHER" },
];
const ROW = {
  id: 1, itemCode: "IT-1", item: "Aliment démarrage", feedStage: "STARTER", coldChain: false,
  threshold: 0, unit: "kg", price: 0, supplier: null, itemType: "", quantity: 10,
  originalQuantity: 10, date: "2026-09-22",
};

const renderForm = () =>
  render(
    <StockParametersForm
      initialData={{ 1: [ROW], 2: [] }}
      initialCategories={CATEGORIES}
      initialSuppliers={[]}
      warehouse={{}}
      showStockEntry
      mode="management"
      farmId={1}
      onSave={vi.fn()}
    />,
  );

describe("StockParametersForm — inline supplier creation", () => {
  beforeEach(() => vi.clearAllMocks());

  test("a rejected creation says why and keeps the typed name on screen", async () => {
    const user = userEvent.setup();
    stockApi.addSupplier.mockRejectedValue({ response: { data: { name: ["Ce fournisseur existe déjà."] } } });
    renderForm();
    const select = screen.getAllByRole("combobox").find((el) => [...el.options].some((o) => o.value === "__new__"));
    await act(async () => { fireEvent.change(select, { target: { value: "__new__" } }); });

    const input = screen.getByPlaceholderText("Nom du fournisseur");
    await user.type(input, "Provenderie du Sud");
    await user.click(screen.getByLabelText("Confirmer"));

    expect(await screen.findByText("Ce fournisseur existe déjà.")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Nom du fournisseur")).toHaveValue("Provenderie du Sud");
  });

  test("confirming an empty name says what is missing instead of doing nothing", async () => {
    const user = userEvent.setup();
    renderForm();
    const select = screen.getAllByRole("combobox").find((el) => [...el.options].some((o) => o.value === "__new__"));
    await act(async () => { fireEvent.change(select, { target: { value: "__new__" } }); });

    await user.click(screen.getByLabelText("Confirmer"));

    expect(await screen.findByText("Saisissez le nom du fournisseur.")).toBeInTheDocument();
    expect(stockApi.addSupplier).not.toHaveBeenCalled();
  });

  test("three confirms in one tick send a single POST", async () => {
    const user = userEvent.setup();
    stockApi.addSupplier.mockResolvedValue({ data: { id: 3, name: "Provenderie du Sud" } });
    renderForm();
    const select = screen.getAllByRole("combobox").find((el) => [...el.options].some((o) => o.value === "__new__"));
    await act(async () => { fireEvent.change(select, { target: { value: "__new__" } }); });

    await user.type(screen.getByPlaceholderText("Nom du fournisseur"), "Provenderie du Sud");
    const confirm = screen.getByLabelText("Confirmer");
    confirm.click();
    confirm.click();
    confirm.click();

    await waitFor(() => expect(stockApi.addSupplier).toHaveBeenCalledTimes(1));
  });
});

// The first version of this fix set `categoryError`, whose only render site is inside the
// "ajouter une catégorie" branch — a branch the delete flow never opens. The state was set and
// nothing on screen could show it, so the live app still failed silently. These pin the render
// site, not just the handler.
describe("StockParametersForm — deleting a category that the server refuses", () => {
  beforeEach(() => vi.clearAllMocks());

  test("the reason appears in the confirmation dialog, which stays open", async () => {
    const user = userEvent.setup();
    stockApi.removeCategory.mockRejectedValue({ response: { data: { detail: "Cette catégorie contient des mouvements." } } });
    renderForm();

    await user.click(screen.getByLabelText("Supprimer la catégorie Litière"));
    await user.click(await screen.findByRole("button", { name: "Supprimer la catégorie" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Cette catégorie contient des mouvements.");
    expect(screen.getByRole("button", { name: "Supprimer la catégorie" })).toBeInTheDocument();
    expect(screen.getByLabelText("Supprimer la catégorie Litière")).toBeInTheDocument();
  });

  test("a successful delete closes the dialog and drops the tab", async () => {
    const user = userEvent.setup();
    stockApi.removeCategory.mockResolvedValue({ data: {} });
    renderForm();

    await user.click(screen.getByLabelText("Supprimer la catégorie Litière"));
    await user.click(await screen.findByRole("button", { name: "Supprimer la catégorie" }));

    await waitFor(() => expect(screen.queryByLabelText("Supprimer la catégorie Litière")).not.toBeInTheDocument());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
