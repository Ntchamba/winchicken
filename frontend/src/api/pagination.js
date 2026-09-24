// Every list endpoint is paginated by 20 (DRF PageNumberPagination). A caller that sums or
// searches a list must read every page, or its answer silently changes at row 21. Pages are
// requested by number, not by following `next`: that absolute URL is built from the Host the
// server saw, which is not always the address the phone reached it on.
const MAX_PAGES = 100;

/**
 * @param {(params: object) => Promise<{data: object[] | {results: object[], next: ?string}}>} get
 * @param {object} [params]
 * @returns {Promise<object[]>} every row, in the endpoint's order
 */
export async function fetchAllPages(get, params = {}) {
  const rows = [];
  for (let page = 1; page <= MAX_PAGES; page += 1) {
    const { data } = await get({ ...params, page });
    if (Array.isArray(data)) return data;
    rows.push(...data.results);
    if (!data.next) break;
  }
  return rows;
}
