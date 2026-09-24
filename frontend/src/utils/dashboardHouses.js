const DAY_MS = 86400000;

/** Whole days between two "YYYY-MM-DD" strings, read as calendar dates (never through the
 * browser's time zone, which can shift a date-only string by a day). Null when either is missing. */
export function daysBetween(startISO, endISO) {
  if (!startISO || !endISO) return null;
  const utc = (iso) => {
    const [y, m, d] = iso.split("-").map(Number);
    return Date.UTC(y, m - 1, d);
  };
  return Math.round((utc(endISO) - utc(startISO)) / DAY_MS);
}

/**
 * The dashboard's house rows: each house with its active batch's day of the cycle, cycle length
 * and headcount against the house's capacity.
 *
 * The day comes from the API (`day_of_cycle`, apps.batches.services.day_of_cycle) — the number the
 * house page, the task list and the reminders all use, counted from 0 on the start date. It used
 * to be recomputed here, 1-based and from the browser's UTC clock, so the dashboard read one day
 * ahead of the house page ("jour 22" vs "Jour 21"). A batch that has not started yet shows day 0.
 *
 * @param {{houseCode: string, maxCapacity?: number}[]} houses
 * @param {{house_code: string, status: string, day_of_cycle: number, start_date: string,
 *   planned_end_date: ?string, current_count: number}[]} batches
 */
export function enrichHouses(houses, batches) {
  const activeByHouse = Object.fromEntries(
    batches.filter((b) => b.status === "ACTIVE").map((b) => [b.house_code, b]),
  );
  return houses.map((house) => {
    const batch = activeByHouse[house.houseCode];
    if (!batch) return { ...house, status: "void", day: null, cycle: null, count: 0, capacity: house.maxCapacity ?? 0 };
    return {
      ...house,
      status: "active",
      day: Math.max(0, batch.day_of_cycle ?? 0),
      cycle: daysBetween(batch.start_date, batch.planned_end_date),
      count: batch.current_count,
      // The house's capacity, not the batch's own count ("594/594 volailles" on every row).
      capacity: house.maxCapacity ?? batch.current_count,
    };
  });
}
