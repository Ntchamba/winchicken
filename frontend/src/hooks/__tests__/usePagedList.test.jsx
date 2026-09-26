import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import usePagedList from "../usePagedList";
import { networkError } from "../../test/networkError";

const page = (n, rows, next) => ({ data: { count: 45, next: next ? `?page=${n + 1}` : null, results: rows } });
const rowsOf = (from, to) => Array.from({ length: to - from }, (_, i) => ({ id: from + i }));

describe("usePagedList", () => {
  test("reads page 1, then appends page after page until there is no next", async () => {
    const fetchPage = vi.fn((n) => Promise.resolve(
      n === 1 ? page(1, rowsOf(0, 20), true) : n === 2 ? page(2, rowsOf(20, 40), true) : page(3, rowsOf(40, 45), false),
    ));
    const { result } = renderHook(() => usePagedList(fetchPage));
    await waitFor(() => expect(result.current.rows).toHaveLength(20));
    expect(result.current).toMatchObject({ count: 45, hasMore: true });

    await act(() => result.current.loadMore());
    await act(() => result.current.loadMore());
    expect(result.current.rows.map((r) => r.id)).toEqual(rowsOf(0, 45).map((r) => r.id));
    expect(result.current.hasMore).toBe(false);
    expect(fetchPage.mock.calls.map(([n]) => n)).toEqual([1, 2, 3]);
  });

  test("reload starts again from page 1 and a late answer to the old list is dropped", async () => {
    let releaseOld;
    const fetchPage = vi.fn()
      .mockResolvedValueOnce(page(1, rowsOf(0, 20), true))
      .mockImplementationOnce(() => new Promise((resolve) => { releaseOld = () => resolve(page(2, rowsOf(20, 40), true)); }))
      .mockResolvedValueOnce(page(1, [{ id: 99 }], false));
    const { result } = renderHook(() => usePagedList(fetchPage));
    await waitFor(() => expect(result.current.rows).toHaveLength(20));

    act(() => { result.current.loadMore(); });
    await act(() => result.current.reload());
    await act(async () => { releaseOld(); });
    expect(result.current.rows).toEqual([{ id: 99 }]);
    expect(result.current.hasMore).toBe(false);
  });

  test("a plain array answer is the whole list", async () => {
    const { result } = renderHook(() => usePagedList(() => Promise.resolve({ data: [{ id: 1 }, { id: 2 }] })));
    await waitFor(() => expect(result.current.rows).toHaveLength(2));
    expect(result.current).toMatchObject({ count: 2, hasMore: false });
  });

  test("a failure is reported, the rows already shown stay", async () => {
    const fetchPage = vi.fn()
      .mockResolvedValueOnce(page(1, rowsOf(0, 20), true))
      .mockRejectedValueOnce(networkError());
    const { result } = renderHook(() => usePagedList(fetchPage));
    await waitFor(() => expect(result.current.rows).toHaveLength(20));
    await act(() => result.current.loadMore());
    expect(result.current.error).toBeInstanceOf(Error);
    expect(result.current.rows).toHaveLength(20);
    expect(result.current.hasMore).toBe(true);
  });
});
