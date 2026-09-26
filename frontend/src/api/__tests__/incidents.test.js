import { beforeEach, describe, expect, test, vi } from "vitest";

const cases = vi.fn();
const faults = vi.fn();
vi.mock("../endpoints", () => ({ maintenanceApi: { cases: (...a) => cases(...a), faults: (...a) => faults(...a) } }));

import { countOf, countOpenIncidents } from "../incidents";
import { networkError } from "../../test/networkError";

describe("countOf", () => {
  test("reads a paginated count, else the array length", () => {
    expect(countOf({ count: 7, results: [1] })).toBe(7);
    expect(countOf({ count: 0, results: [] })).toBe(0);
    expect(countOf({ results: [1, 2] })).toBe(2);
    expect(countOf([1, 2, 3])).toBe(3);
    expect(countOf([])).toBe(0);
  });
});

describe("countOpenIncidents", () => {
  beforeEach(() => {
    cases.mockReset();
    faults.mockReset();
  });

  test("adds unresolved cases and open faults, farm-wide", async () => {
    cases.mockResolvedValue({ data: { count: 2, results: [] } });
    faults.mockResolvedValue({ data: [{}, {}, {}] });
    expect(await countOpenIncidents()).toBe(5);
    expect(cases).toHaveBeenCalledWith({ resolved: "false" });
    expect(faults).toHaveBeenCalledWith({ status: "OPEN" });
  });

  test("scoped to one house when given", async () => {
    cases.mockResolvedValue({ data: [] });
    faults.mockResolvedValue({ data: [] });
    expect(await countOpenIncidents("H-1")).toBe(0);
    expect(cases).toHaveBeenCalledWith({ house_code: "H-1", resolved: "false" });
    expect(faults).toHaveBeenCalledWith({ house_code: "H-1", status: "OPEN" });
  });

  test("a failed request rejects instead of reporting zero", async () => {
    cases.mockRejectedValue(networkError());
    faults.mockResolvedValue({ data: [] });
    await expect(countOpenIncidents()).rejects.toThrow("Network Error");
  });
});
