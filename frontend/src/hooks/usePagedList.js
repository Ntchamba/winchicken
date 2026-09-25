import { useCallback, useEffect, useRef, useState } from "react";

/**
 * A paginated list shown page by page, "Afficher plus" appending the next one.
 *
 * Every list endpoint returns 20 rows a page, and the screens that grow over time (employees,
 * alerts, incidents, salary payments) only ever read page 1: the 21st employee simply did not
 * exist on screen — real at 40 staff (load test, 2026-09-25). Reading every page up front
 * (`fetchAllPages`) is right for short reference lists; for these, it would be a thousand
 * requests at 20 000 employees, so the user asks for more instead.
 *
 * `fetchPage` must be stable (module-level or `useCallback`) — a new function reloads page 1.
 *
 * @param {(page: number) => Promise<{data: object[] | {results: object[], next: ?string, count?: number}}>} fetchPage
 * @param {{enabled?: boolean}} [options] - `enabled: false` waits (e.g. until a role is known).
 */
export default function usePagedList(fetchPage, { enabled = true } = {}) {
  const [rows, setRows] = useState([]);
  const [count, setCount] = useState(null);
  const [nextPage, setNextPage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  // Answers to an older reload (or to a page of a list since reloaded) are dropped.
  const generation = useRef(0);

  const loadPage = useCallback(async (page, gen) => {
    setLoading(true);
    try {
      const { data } = await fetchPage(page);
      if (gen !== generation.current) return;
      const pageRows = Array.isArray(data) ? data : data.results;
      setRows((prev) => (page === 1 ? pageRows : [...prev, ...pageRows]));
      setCount(Array.isArray(data) ? data.length : data.count ?? null);
      setNextPage(!Array.isArray(data) && data.next ? page + 1 : null);
      setError(null);
    } catch (err) {
      if (gen === generation.current) setError(err);
    } finally {
      if (gen === generation.current) setLoading(false);
    }
  }, [fetchPage]);

  const reload = useCallback(() => {
    generation.current += 1;
    return loadPage(1, generation.current);
  }, [loadPage]);

  const loadMore = useCallback(() => {
    if (nextPage == null || loading) return undefined;
    return loadPage(nextPage, generation.current);
  }, [loadPage, nextPage, loading]);

  useEffect(() => {
    if (enabled) reload();
  }, [enabled, reload]);

  return { rows, setRows, count, hasMore: nextPage != null, loading, error, reload, loadMore };
}
