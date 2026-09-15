import { describe, expect, test } from "vitest";

import { buildProtocolSchedules, makeRow } from "../protocolRows";

// One builder, because there used to be two. HouseProtocolPage's copy omitted the consumption
// fields, so saving a protocol from the full-page route sent stock_item: null for every line
// and silently dropped the farm's whole deduction config. ProtocolEditModal's copy had them.

const CATEGORIES = [{ id: 1, label: "Alimentation" }, { id: 2, label: "Santé et soins" }];

const LINE = {
  id: 42,
  category: 1,
  from_value: 1,
  from_unit: "DAY",
  to_value: 15,
  to_unit: "DAY",
  until_end: false,
  what: "Aliment démarrage",
  details: "3000 kcal",
  time_slots: [{ id: 7, start_time: "06:30:00", end_time: "07:30:00" }],
  stock_item: "FEE-1-001",
  quantity_per_day: 40,
  dose_per_bird: null,
};

describe("buildProtocolSchedules", () => {
  test("carries the consumption config through", () => {
    const [row] = buildProtocolSchedules(CATEGORIES, [LINE])[1];
    expect(row.stockItemCode).toBe("FEE-1-001");
    expect(row.consumptionMode).toBe("fixed");
    expect(row.quantityPerDay).toBe(40);
    expect(row.dosePerBird).toBe("");
  });

  test("a per-bird dose comes back in dose mode", () => {
    const [row] = buildProtocolSchedules(
      CATEGORIES, [{ ...LINE, quantity_per_day: null, dose_per_bird: 0.5 }],
    )[1];
    expect(row.consumptionMode).toBe("dose");
    expect(row.dosePerBird).toBe(0.5);
  });

  test("the database id is kept as serverId, never as the local row id", () => {
    const [row] = buildProtocolSchedules(CATEGORIES, [LINE])[1];
    expect(row.serverId).toBe(42);
    // The local id comes from the shared counter, which starts at 100 and would otherwise be
    // able to collide with a real database id and edit an unrelated line.
    expect(row.id).not.toBe(42);
    expect(row.id).toBeGreaterThanOrEqual(100);
  });

  test("a row added in the form has no serverId, so the backend creates it", () => {
    expect(makeRow().serverId).toBeUndefined();
  });

  test("local ids stay unique across rows and across calls", () => {
    const first = buildProtocolSchedules(CATEGORIES, [LINE, { ...LINE, id: 43 }])[1];
    const second = buildProtocolSchedules(CATEGORIES, [LINE])[1];
    const ids = [...first, ...second, makeRow()].map((r) => r.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  test("lines land under their own category and time slots are mapped", () => {
    const map = buildProtocolSchedules(CATEGORIES, [LINE, { ...LINE, id: 43, category: 2 }]);
    expect(map[1]).toHaveLength(1);
    expect(map[2]).toHaveLength(1);
    expect(map[1][0].timeSlots).toEqual([{ id: 7, startTime: "06:30:00", endTime: "07:30:00" }]);
  });
});
