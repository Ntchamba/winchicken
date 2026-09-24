import { describe, expect, test, vi } from "vitest";

import { resolveProtocolImportRows } from "../protocolImportResolve";

// Re-importing a protocol replaces the form's rows with the file's. Rows built with no server id
// are *new* lines to the PUT, so every existing line was deleted and recreated — and its task
// completions went with it (CASCADE): today's done tasks read as outstanding again and a re-tap
// deducted the stock twice (FIX 3.5 bug A, back through the import door). A file line that is
// the same task as an existing line must keep that line's id.

const categories = [{ id: 3, label: "Alimentation" }, { id: 4, label: "Vaccination" }];
const deps = { categories, stockItemList: [], farmId: 1, createCategory: vi.fn(), createStockItem: vi.fn() };
const fileRow = (over) => ({ category: "Alimentation", fromValue: 1, toValue: null, untilEnd: true, what: "Aliment démarrage", details: "", timeSlots: [], ...over });
const existingRow = (over) => ({ serverId: 91, fromValue: 1, fromUnit: "Day", toValue: 1, toUnit: "Day", untilEnd: true, what: "Aliment démarrage", ...over });

describe("resolveProtocolImportRows — existing lines keep their id", () => {
  test("a file line matching an existing line (category, task, days) carries its serverId", async () => {
    const { schedules } = await resolveProtocolImportRows(
      { rows: [fileRow({ details: "modifié" }), fileRow({ category: "Vaccination", what: "Gumboro", fromValue: 7, toValue: 7, untilEnd: false })] },
      { ...deps, existingSchedules: { 3: [existingRow()], 4: [existingRow({ serverId: 92, what: "Gumboro", fromValue: 7, toValue: 7, untilEnd: false })] } },
    );
    expect(schedules[3].map((r) => [r.serverId, r.details])).toEqual([[91, "modifié"]]);
    expect(schedules[4].map((r) => r.serverId)).toEqual([92]);
  });

  test("case and spacing of the task name do not matter", async () => {
    const { schedules } = await resolveProtocolImportRows(
      { rows: [fileRow({ what: "  aliment DÉMARRAGE " })] },
      { ...deps, existingSchedules: { 3: [existingRow()] } },
    );
    expect(schedules[3][0].serverId).toBe(91);
  });

  test("a different day range or category is a new line", async () => {
    const { schedules } = await resolveProtocolImportRows(
      { rows: [fileRow({ fromValue: 2 }), fileRow({ category: "Vaccination" })] },
      { ...deps, existingSchedules: { 3: [existingRow()] } },
    );
    expect(schedules[3][0].serverId).toBeUndefined();
    expect(schedules[4][0].serverId).toBeUndefined();
  });

  test("one existing line is claimed once, even if the file repeats the task", async () => {
    const { schedules } = await resolveProtocolImportRows(
      { rows: [fileRow(), fileRow()] },
      { ...deps, existingSchedules: { 3: [existingRow()] } },
    );
    expect(schedules[3].map((r) => r.serverId)).toEqual([91, undefined]);
  });

  test("without existing schedules (onboarding, a new house) every line is new", async () => {
    const { schedules } = await resolveProtocolImportRows({ rows: [fileRow()] }, deps);
    expect(schedules[3][0].serverId).toBeUndefined();
  });
});
