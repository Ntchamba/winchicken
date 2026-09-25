import { describe, expect, test } from "vitest";
import { formatNumber } from "../numberFormat";

describe("formatNumber", () => {
  test("French decimal comma, no trailing zeros", () => {
    expect(formatNumber("10.00")).toBe("10");
    expect(formatNumber("7.50")).toBe("7,5");
    expect(formatNumber(0.25)).toBe("0,25");
  });
  test("thousands grouped with a space", () => {
    expect(formatNumber(1234.5).replace(/\s/g, " ")).toBe("1 234,5");
  });
  test("nothing to show is a dash", () => {
    expect(formatNumber(null)).toBe("—");
    expect(formatNumber("")).toBe("—");
    expect(formatNumber("abc")).toBe("—");
  });
});
