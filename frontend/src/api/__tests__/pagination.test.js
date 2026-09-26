import { describe, expect, test, vi } from "vitest";

import { fetchAllPages } from "../pagination";
import { networkError } from "../../test/networkError";

// Every list endpoint is paginated by 20. A caller that sums or searches a list must read every
// page, or its answer silently changes at row 21 ("Ventes du jour" short from the 21st sale).

const pages = (...rows) => vi.fn(({ page }) => Promise.resolve({
  data: { count: rows.flat().length, next: page < rows.length ? `?page=${page + 1}` : null, results: rows[page - 1] },
}));

describe("fetchAllPages", () => {
  test("follows the pages until there is no next one, keeping the caller's params", async () => {
    const get = pages([1, 2], [3, 4], [5]);
    expect(await fetchAllPages(get, { sale_date: "2026-09-24" })).toEqual([1, 2, 3, 4, 5]);
    expect(get.mock.calls.map(([p]) => p)).toEqual([
      { sale_date: "2026-09-24", page: 1 },
      { sale_date: "2026-09-24", page: 2 },
      { sale_date: "2026-09-24", page: 3 },
    ]);
  });

  test("an unpaginated endpoint (a bare array) is returned as is, in one call", async () => {
    const get = vi.fn(() => Promise.resolve({ data: [7, 8] }));
    expect(await fetchAllPages(get)).toEqual([7, 8]);
    expect(get).toHaveBeenCalledTimes(1);
  });

  test("a failing page rejects the whole read instead of returning a partial list", async () => {
    const get = vi.fn()
      .mockResolvedValueOnce({ data: { next: "?page=2", results: [1] } })
      .mockRejectedValueOnce(networkError());
    await expect(fetchAllPages(get)).rejects.toThrow("Network Error");
  });
});
