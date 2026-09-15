import { render, screen, act, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import StockParametersForm from "../StockParametersForm";

// The "Date" cell of every stock row is seeded with the local day the rows were built, and this
// is a screen a worker leaves open all day. Crossing farm-local midnight used to leave the cell
// on yesterday while the save still went through — filing the opening-stock IN movement against
// the wrong day. Same rule as `useDateDefaultingToToday`, applied across a table of rows.

let fakeToday = "2026-09-15";
vi.mock("../../utils/localDate", () => ({
  todayISO: () => fakeToday,
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
    addSupplier: vi.fn(),
  },
}));

const CATEGORIES = [{ id: 1, label: "Aliment", icon: "Wheat", kind: "FEED" }];

const row = (id, name, date) => ({
  id,
  itemCode: `IT-${id}`,
  item: name,
  feedStage: "STARTER",
  coldChain: false,
  threshold: 0,
  unit: "kg",
  price: 0,
  supplier: null,
  itemType: "",
  quantity: 10,
  originalQuantity: 10,
  date,
});

const crossMidnightTo = async (day) => {
  fakeToday = day;
  await act(async () => {
    document.dispatchEvent(new Event("visibilitychange"));
  });
};

const renderForm = (rows) =>
  render(
    <StockParametersForm
      initialData={{ 1: rows }}
      initialCategories={CATEGORIES}
      initialSuppliers={[]}
      warehouse={{}}
      showStockEntry
      mode="management"
      onSave={vi.fn()}
    />,
  );

describe("StockParametersForm — the row Date cell crossing farm-local midnight", () => {
  beforeEach(() => {
    fakeToday = "2026-09-15";
  });

  test("a cell still showing the previous today rolls forward", async () => {
    renderForm([row(1, "Aliment démarrage", "2026-09-15")]);
    expect(screen.getByLabelText("Date").value).toBe("2026-09-15");

    await crossMidnightTo("2026-09-16");

    expect(screen.getByLabelText("Date").value).toBe("2026-09-16");
  });

  test("a deliberately backdated cell is left alone while its neighbour rolls", async () => {
    renderForm([row(1, "Aliment démarrage", "2026-09-15"), row(2, "Aliment croissance", "2026-09-15")]);
    const [first, second] = screen.getAllByLabelText("Date");

    // fireEvent.change goes through React's value tracker; assigning `.value` would not fire
    // onChange at all.
    await act(async () => {
      fireEvent.change(first, { target: { value: "2026-09-10" } });
    });

    await crossMidnightTo("2026-09-16");

    expect(first.value).toBe("2026-09-10");
    expect(second.value).toBe("2026-09-16");
  });

  test("it keeps following across two successive midnights", async () => {
    renderForm([row(1, "Aliment démarrage", "2026-09-15")]);

    await crossMidnightTo("2026-09-16");
    await crossMidnightTo("2026-09-17");

    expect(screen.getByLabelText("Date").value).toBe("2026-09-17");
  });
});
