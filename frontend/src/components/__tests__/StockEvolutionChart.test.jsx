import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";
import StockEvolutionChart from "../StockEvolutionChart";

// recharts' ResponsiveContainer needs a non-zero size in jsdom; stub it to a plain div.
vi.mock("recharts", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, ResponsiveContainer: ({ children }) => <div style={{ width: 800, height: 300 }}>{children}</div> };
});

const SERIES = [
  { itemCode: "FEE-1-001", name: "Aliment démarrage", unit: "kg", alertThreshold: 50, points: [
    { date: "2026-01-01", quantity: 100 }, { date: "2026-01-03", quantity: 70 },
  ] },
  { itemCode: "VET-1-001", name: "Vaccin", unit: "dose", alertThreshold: 10, points: [] },
];

describe("StockEvolutionChart", () => {
  test("empty state when no item has movements", () => {
    render(<StockEvolutionChart series={[{ itemCode: "X", name: "X", unit: "kg", alertThreshold: 0, points: [] }]} />);
    expect(screen.getByText(/Aucun mouvement de stock/)).toBeInTheDocument();
  });

  test("lists only items that have points in the selector", async () => {
    render(<StockEvolutionChart series={SERIES} />);
    const select = screen.getByLabelText("Choisir un article");
    // "Tous les articles" + the one item with points; the empty "Vaccin" is excluded.
    expect(select).toHaveTextContent("Aliment démarrage");
    expect(select).not.toHaveTextContent("Vaccin");
    await userEvent.selectOptions(select, "FEE-1-001");
    expect(select).toHaveValue("FEE-1-001");
  });
});
