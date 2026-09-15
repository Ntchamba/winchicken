import React from "react";
import { render, screen, act, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { useDateDefaultingToToday } from "../useTodayISO";

// Workers leave this app open on a phone all day, so a date field mounted in the evening is
// still mounted after local midnight. These pin the roll-over down.
//
// The regression that made this file exist: the effect scheduled a functional `setValue` and
// then assigned `previousTodayRef.current = today` on the next line. The updater runs during
// the *next render*, by which point the ref already held the new day, so the
// "is the field still showing the previous today?" comparison could never be true and the
// field never rolled over — while `max`, read straight from `today`, did. Caught live in a
// real browser at 23h30 -> 00h30 Africa/Douala, not by the unit suite of the day.

let fakeToday = "2026-09-15";
vi.mock("../../utils/localDate", () => ({
  todayISO: () => fakeToday,
  toLocalISODate: (v) => v,
}));

function Probe() {
  const [value, setValue, today] = useDateDefaultingToToday();
  return (
    <input
      aria-label="date"
      type="date"
      value={value}
      max={today}
      onChange={(e) => setValue(e.target.value)}
    />
  );
}

const crossMidnightTo = async (day) => {
  fakeToday = day;
  await act(async () => {
    document.dispatchEvent(new Event("visibilitychange"));
  });
};

describe("useDateDefaultingToToday — crossing farm-local midnight with the screen open", () => {
  beforeEach(() => {
    fakeToday = "2026-09-15";
  });

  test("an untouched field follows the new day, and max follows with it", async () => {
    render(<Probe />);
    const input = screen.getByLabelText("date");
    expect(input.value).toBe("2026-09-15");

    await crossMidnightTo("2026-09-16");

    expect(input.value).toBe("2026-09-16");
    expect(input.max).toBe("2026-09-16");
  });

  test("it keeps following across two successive midnights", async () => {
    render(<Probe />);
    const input = screen.getByLabelText("date");

    await crossMidnightTo("2026-09-16");
    await crossMidnightTo("2026-09-17");

    expect(input.value).toBe("2026-09-17");
  });

  test("a deliberately backdated field is left alone", async () => {
    render(<Probe />);
    const input = screen.getByLabelText("date");

    // fireEvent.change goes through React's value tracker; assigning `.value` directly does
    // not, and onChange would never fire.
    await act(async () => {
      fireEvent.change(input, { target: { value: "2026-09-10" } });
    });
    expect(input.value).toBe("2026-09-10");

    await crossMidnightTo("2026-09-16");

    // The correction the worker typed survives; only `max` moves.
    expect(input.value).toBe("2026-09-10");
    expect(input.max).toBe("2026-09-16");
  });
});
