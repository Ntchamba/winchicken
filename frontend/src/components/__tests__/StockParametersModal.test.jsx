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
  },
}));

vi.mock("../StockParametersForm", () => ({
  default: ({ onSave }) => (
    <button onClick={() => onSave({ items: [{ category: 1, name: "Aliment", unit: "kg" }] })}>Fake Save</button>
  ),
}));

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

  test("does not fetch while closed", () => {
    render(<StockParametersModal open={false} farmId={7} onClose={onClose} onSaved={onSaved} />);
    expect(stockApi.categories).not.toHaveBeenCalled();
  });
});
