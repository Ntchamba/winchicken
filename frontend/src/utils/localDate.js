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
