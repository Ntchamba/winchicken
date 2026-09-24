import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import StockParametersModal from "../StockParametersModal";
import { stockApi } from "../../api/endpoints";

// The stock parameter form only opens via this modal now (Part A). This pins the two things
// the modal owns: it loads categories + items + suppliers, and on the form's save it persists
// via putItems, then closes and fires onSaved (the live-refresh hook for the charts below it).

vi.mock("../../api/endpoints", () => ({
  stockApi: {
    categories: vi.fn(),
    items: vi.fn(),
    suppliers: vi.fn(),
    putItems: vi.fn(),
    importXlsx: vi.fn(),
    importTemplateUrl: "http://test/stock-items/import-template.xlsx",
  },
}));

const formProps = vi.hoisted(() => vi.fn());
vi.mock("../StockParametersForm", () => ({
  default: (props) => {
    formProps(props);
    return <button onClick={() => props.onSave({ items: [{ category: 1, name: "Aliment", unit: "kg" }] })}>Fake Save</button>;
  },
}));

const paged = (rows) => ({ page }) => Promise.resolve({
  data: { count: rows.length, next: page * 20 < rows.length ? `?page=${page + 1}` : null, results: rows.slice((page - 1) * 20, page * 20) },
});

describe("StockParametersModal", () => {
  const onClose = vi.fn();
  const onSaved = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    stockApi.categories.mockResolvedValue({ data: [{ id: 1, label: "Aliment", icon: "Wheat", kind: "FEED" }] });
    stockApi.items.mockResolvedValue({ data: { items: [] } });
    stockApi.suppliers.mockResolvedValue({ data: [] });
    stockApi.putItems.mockResolvedValue({ data: { items: [] } });
  });

  test("save persists items then closes and refreshes", async () => {
    render(<StockParametersModal open farmId={7} onClose={onClose} onSaved={onSaved} />);

    const saveButton = await screen.findByText("Fake Save");
    await userEvent.click(saveButton);

    await waitFor(() => expect(stockApi.putItems).toHaveBeenCalledWith(7, [{ category: 1, name: "Aliment", unit: "kg" }]));
    expect(onSaved).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  // The save PUTs the items of the categories the form was given, and the server deletes every
  // item it is not sent (stock/views.py) — CASCADE to its movements, vaccinations, compositions
  // and purchase orders. Categories are paginated by 20: page 1 only would have wiped the 21st.
  test("the form gets every category and every supplier, past the first page", async () => {
    const cats = Array.from({ length: 21 }, (_, i) => ({ id: i + 1, label: `Cat ${i + 1}`, icon: "Box", kind: "OTHER" }));
    const sups = Array.from({ length: 21 }, (_, i) => ({ id: i + 1, name: `Fournisseur ${i + 1}` }));
    stockApi.categories.mockImplementation((farmId, params) => paged(cats)(params));
    stockApi.suppliers.mockImplementation((farmId, params) => paged(sups)(params));

    render(<StockParametersModal open farmId={7} onClose={onClose} onSaved={onSaved} />);
    await screen.findByText("Fake Save");

    const props = formProps.mock.calls.at(-1)[0];
    expect(props.initialCategories).toHaveLength(21);
    expect(props.initialSuppliers).toHaveLength(21);
  });

  test("does not fetch while closed", () => {
    render(<StockParametersModal open={false} farmId={7} onClose={onClose} onSaved={onSaved} />);
    expect(stockApi.categories).not.toHaveBeenCalled();
  });

  test("Excel import posts the file, shows the update/create/skip summary, and refreshes", async () => {
    stockApi.importXlsx.mockResolvedValue({
      data: { updated: 1, created: 1, skipped: [{ line: 4, reason: "catégorie manquante" }] },
    });
    const { container } = render(<StockParametersModal open farmId={7} onClose={onClose} onSaved={onSaved} />);
    await screen.findByText("Fake Save");

    stockApi.categories.mockClear();
    await userEvent.upload(container.querySelector('input[type="file"]'), new File(["x"], "stock.xlsx"));

    await waitFor(() => expect(stockApi.importXlsx).toHaveBeenCalledWith(7, expect.any(File)));
    expect(await screen.findByText(/1 ligne mise à jour, 1 ligne créée, 1 ligne ignorée/i)).toBeInTheDocument();
    expect(screen.getByText("Ligne 4 : catégorie manquante")).toBeInTheDocument();
    expect(stockApi.categories).toHaveBeenCalled(); // reloaded after import
    expect(onSaved).toHaveBeenCalled();
  });
});
