/**
 * Today's date as `YYYY-MM-DD`, in the *browser's* local timezone.
 *
 * Every form in this app used to build that string with
 * `new Date().toISOString().slice(0, 10)`, which is the UTC date, not the local one. On a farm
 * running at UTC+1 (Africa/Douala, the default `FARM_TIME_ZONE`) that is wrong for the first
 * hour of every day: at 00:30 local, `toISOString()` still reports yesterday, so a daily log
 * entered just after midnight was saved against the previous day — and, because
 * `DailyLog` is unique on `(batch, log_date)`, it could collide with the entry already there.
 *
 * `sv-SE` is used only because its locale format is exactly `YYYY-MM-DD`; the value it returns
 * is the local calendar date, which is what every `DateField` in the API expects.
 */
export function todayISO() {
  return new Date().toLocaleDateString("sv-SE");
}

/** Same thing for an arbitrary `Date` — local calendar date, never shifted by the UTC offset. */
export function toLocalISODate(value) {
  return new Date(value).toLocaleDateString("sv-SE");
}

/** "2026-09-21" -> "21/09/2026", by string, so no time zone can move the day. Anything that is
 * not a `YYYY-MM-DD` date comes back unchanged. */
export function formatDateFR(iso) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso ?? ""));
  return match ? `${match[3]}/${match[2]}/${match[1]}` : iso;
}
