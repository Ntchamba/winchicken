import { describe, expect, it } from "vitest";
import { financeVerdict } from "../financeVerdict";

describe("financeVerdict", () => {
  it("says the farm is losing money when cash on hand is negative", () => {
    const v = financeVerdict({ access: "full", cashOnHand: -1250000 });
    expect(v.label).toBe("Vous perdez de l'argent");
    expect(v.tier).toBe("critical");
    expect(v.detail).toMatch(/^Trésorerie : -1\s250\s000 FCFA$/);
  });

  it("says the farm is making money when cash on hand is positive", () => {
    const v = financeVerdict({ access: "full", cashOnHand: 300000 });
    expect(v.label).toBe("Vous gagnez de l'argent");
    expect(v.tier).toBe("good");
  });

  it("is neutral at exactly zero", () => {
    expect(financeVerdict({ access: "full", cashOnHand: 0 }).tier).toBe("watch");
  });

  it("returns null for the restricted view, which has no amounts", () => {
    expect(financeVerdict({ access: "restricted", revenueTrend: "up" })).toBeNull();
    expect(financeVerdict(null)).toBeNull();
  });
});
