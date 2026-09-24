import { describe, expect, test } from "vitest";
import { daysBetween, enrichHouses } from "../dashboardHouses";

const batch = (over = {}) => ({
  house_code: "H1", status: "ACTIVE", day_of_cycle: 21, start_date: "2026-09-01",
  planned_end_date: "2026-10-27", current_count: 594, ...over,
});

describe("daysBetween", () => {
  test("counts calendar days, whatever the browser's time zone", () => {
    expect(daysBetween("2026-09-01", "2026-10-27")).toBe(56);
    expect(daysBetween("2026-09-01", "2026-09-01")).toBe(0);
    // Across the end of March (a DST change in Europe) and a leap day.
    expect(daysBetween("2024-02-28", "2024-03-31")).toBe(32);
  });

  test("is null when a date is missing", () => {
    expect(daysBetween("2026-09-01", null)).toBeNull();
    expect(daysBetween(undefined, "2026-09-01")).toBeNull();
  });
});

describe("enrichHouses", () => {
  const houses = [{ houseCode: "H1", name: "Poulailler Nord", maxCapacity: 600 }];

  test("uses the API's day of the cycle, not a second computation", () => {
    const [row] = enrichHouses(houses, [batch({ day_of_cycle: 21 })]);
    expect(row).toMatchObject({ status: "active", day: 21, cycle: 56, count: 594, capacity: 600 });
  });

  test("the start date is day 0", () => {
    expect(enrichHouses(houses, [batch({ day_of_cycle: 0 })])[0].day).toBe(0);
  });

  test("a batch that has not started yet shows day 0, not a negative day", () => {
    expect(enrichHouses(houses, [batch({ day_of_cycle: -3 })])[0].day).toBe(0);
  });

  test("capacity is the house's, not the batch's own headcount", () => {
    expect(enrichHouses(houses, [batch({ current_count: 594 })])[0].capacity).toBe(600);
  });

  test("a house without an active batch is a sanitary void", () => {
    const rows = enrichHouses(houses, [batch({ status: "CLOSED" })]);
    expect(rows[0]).toMatchObject({ status: "void", day: null, cycle: null, count: 0, capacity: 600 });
  });

  test("no planned end date means no cycle length", () => {
    expect(enrichHouses(houses, [batch({ planned_end_date: null })])[0].cycle).toBeNull();
  });
});
