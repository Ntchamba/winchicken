import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

vi.mock("../../api/endpoints", () => ({
  batchesApi: {
    dailyLogs: vi.fn(() => Promise.resolve({ data: [
      { id: 1, log_date: "2026-09-20", avg_sample_weight: 1.05 },
      { id: 2, log_date: "2026-09-21", avg_sample_weight: 1.106 },
      { id: 3, log_date: "2026-09-22", avg_sample_weight: null },
    ] })),
    quickEntry: vi.fn(),
  },
}));

import WeighingSection from "../WeighingSection";

describe("WeighingSection — recent weighings", () => {
  test("French dates and decimals, newest first, days without a weighing left out", async () => {
    render(<WeighingSection batches={[{ batchCode: "B1", name: "Bande Nord" }]} />);
    const items = await screen.findAllByRole("listitem");
    expect(items.map((li) => li.textContent)).toEqual(["21/09/2026 — 1,106 kg", "20/09/2026 — 1,05 kg"]);
  });
});
