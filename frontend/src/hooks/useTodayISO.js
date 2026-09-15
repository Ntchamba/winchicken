import { useCallback, useEffect, useRef, useState } from "react";

import { todayISO } from "../utils/localDate";

/**
 * The farm-local date as `YYYY-MM-DD`, kept current for as long as the component lives.
 *
 * `todayISO()` read once in `useState` is wrong here, and not theoretically: workers keep this
 * app open on a phone all day on a single screen and rarely navigate, so a component mounted at
 * 14h is still mounted at 00h30 — with yesterday's date baked into its state while
 * `max={todayISO()}`, re-evaluated on every render, already shows today. That is the silent
 * mis-dating the farm-local-time work exists to end.
 *
 * Re-reads on three signals, all of them cheap:
 * - `visibilitychange` — the phone was unlocked or the tab came back to the foreground, which is
 *   what actually happens between the evening and the night check;
 * - `focus` — the window was refocused on a desktop;
 * - a single timer armed for the next local midnight, so a screen left visible and focused
 *   across midnight still rolls over on its own.
 *
 * The timer is re-armed after each tick rather than set on an interval: an interval would drift
 * away from midnight, and one timeout per day costs nothing.
 */
export function useTodayISO() {
  const [today, setToday] = useState(todayISO);
  const timerRef = useRef(null);

  const sync = useCallback(() => {
    // Functional update: React skips the re-render when the string is unchanged, so the common
    // case (a tab foregrounded on the same day) costs one comparison.
    setToday((current) => {
      const next = todayISO();
      return next === current ? current : next;
    });
  }, []);

  useEffect(() => {
    const armMidnight = () => {
      const now = new Date();
      const nextMidnight = new Date(now);
      nextMidnight.setHours(24, 0, 0, 500); // 500 ms past, so the date has definitely rolled
      timerRef.current = window.setTimeout(() => {
        sync();
        armMidnight();
      }, nextMidnight.getTime() - now.getTime());
    };

    const onVisible = () => {
      if (document.visibilityState === "visible") sync();
    };

    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", sync);
    armMidnight();

    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", sync);
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, [sync]);

  return today;
}

/**
 * A date form field that defaults to today and *keeps* defaulting to today — until the user
 * picks something else, after which their choice is left alone.
 *
 * Every date field in this app is editable on purpose (a correction or a backdated entry is a
 * normal thing to record), so the roll-over must not overwrite a deliberate choice. It follows
 * `today` only while the field still holds the previous `today`.
 *
 * Returns `[value, setValue, today]` — `today` is exposed because these forms also use it for
 * `max`, and the two must come from the same read or they can disagree mid-render.
 */
export function useDateDefaultingToToday() {
  const today = useTodayISO();
  const [value, setValue] = useState(today);
  const previousTodayRef = useRef(today);

  useEffect(() => {
    // Read the ref into a local *before* scheduling, and let the updater close over that local.
    // A functional updater runs during the next render, not here, so an updater that read
    // `previousTodayRef.current` would see the value assigned on the line below rather than the
    // previous day — the comparison would never hold and the field would never roll over.
    // (StrictMode also double-invokes updaters, so it has to be pure with respect to the ref.)
    const previousToday = previousTodayRef.current;
    if (previousToday === today) return;
    previousTodayRef.current = today;
    setValue((current) => (current === previousToday ? today : current));
  }, [today]);

  return [value, setValue, today];
}
