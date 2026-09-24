import { describe, expect, test } from "vitest";
import { formatDateFR } from "../localDate";

describe("formatDateFR", () => {
  test("day/month/year, by string", () => {
    expect(formatDateFR("2026-09-21")).toBe("21/09/2026");
    expect(formatDateFR("2026-01-01")).toBe("01/01/2026");
  });

  test("anything else is returned unchanged", () => {
    expect(formatDateFR("")).toBe("");
    expect(formatDateFR(null)).toBe(null);
    expect(formatDateFR("21/09/2026")).toBe("21/09/2026");
    expect(formatDateFR("2026-09-21T10:00:00Z")).toBe("2026-09-21T10:00:00Z");
  });
});
