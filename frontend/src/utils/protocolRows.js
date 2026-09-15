import {
  Soup, Thermometer, Stethoscope, Syringe, SprayCan, ShieldCheck, Droplets, Wind, Egg, Bug,
  ClipboardList, Package,
} from "lucide-react";

// Moved out of HouseProtocolForm (2026-09-11) so the onboarding Excel-import screen builds
// protocol rows through the exact same factory the form uses — one shared `nextId` counter
// matters here: two independent counters would hand the same row id to rows that later live
// in the same schedules map.

// Curated icon picker for custom categories — kept in sync by hand with the backend's
// CUSTOM_CATEGORY_ICON_CHOICES (apps/protocols/models.py). The 5 defaults' own icons are a
// subset of this same list, so one map covers both.
export const ICON_OPTIONS = [
  { name: "Soup", Icon: Soup }, { name: "Thermometer", Icon: Thermometer },
  { name: "Stethoscope", Icon: Stethoscope }, { name: "Syringe", Icon: Syringe },
  { name: "SprayCan", Icon: SprayCan }, { name: "ShieldCheck", Icon: ShieldCheck },
  { name: "Droplets", Icon: Droplets }, { name: "Wind", Icon: Wind },
  { name: "Egg", Icon: Egg }, { name: "Bug", Icon: Bug },
  { name: "ClipboardList", Icon: ClipboardList }, { name: "Package", Icon: Package },
];
const ICON_MAP = Object.fromEntries(ICON_OPTIONS.map((o) => [o.name, o.Icon]));
export const iconFor = (name) => ICON_MAP[name] || ClipboardList;

// Mirrors apps.protocols.models.DEFAULT_PROTOCOL_CATEGORIES exactly (label + icon + order) —
// used as the starting category list in onboarding mode, before the house (and its real,
// backend-seeded categories) exists. `id` here is a stable local key, not a database id.
export const DEFAULT_CATEGORIES = [
  { id: "default-0", label: "Alimentation", icon: "Soup" },
  { id: "default-1", label: "Température", icon: "Thermometer" },
  { id: "default-2", label: "Santé et soins", icon: "Stethoscope" },
  { id: "default-3", label: "Vaccination", icon: "Syringe" },
  { id: "default-4", label: "Nettoyage", icon: "SprayCan" },
];

let nextId = 100;
export const nextRowId = () => nextId++;

/**
 * `GET /houses/{code}/protocol/` lines -> `{ [categoryId]: [row] }` for `HouseProtocolForm`.
 *
 * There is one builder because there used to be two, and they disagreed: the full-page route
 * (`HouseProtocolPage`) omitted `stockItemCode` / `consumptionMode` / `quantityPerDay` /
 * `dosePerBird`, so `consumptionFields` read them as undefined and saving from that route
 * dropped every line's stock consumption config. The modal's copy had them. Same shape of bug
 * as the two stock-row mappers (see `utils/stockRows.js`).
 *
 * `serverId` is the row's database id, and it is deliberately NOT `id`: `id` is the local key
 * this module hands out from a counter starting at 100, which can collide with a real database
 * id. `HouseProtocolForm` sends `serverId` back as `id` so the PUT can update the line in place
 * instead of deleting and recreating it — which used to take its completion history with it
 * (FIX 3.5, bug A). A row with no `serverId` is new and gets created.
 */
export function buildProtocolSchedules(categories, lines) {
  const map = Object.fromEntries(categories.map((c) => [c.id, []]));
  for (const line of lines) {
    map[line.category]?.push({
      id: nextId++,
      serverId: line.id,
      fromValue: line.from_value,
      fromUnit: line.from_unit.charAt(0) + line.from_unit.slice(1).toLowerCase(),
      toValue: line.to_value || 1,
      toUnit: line.to_unit.charAt(0) + line.to_unit.slice(1).toLowerCase(),
      untilEnd: line.until_end,
      what: line.what,
      details: line.details,
      timeSlots: (line.time_slots || []).map((slot) => ({
        id: slot.id, startTime: slot.start_time, endTime: slot.end_time,
      })),
      stockItemCode: line.stock_item || null,
      consumptionMode: line.dose_per_bird != null ? "dose" : "fixed",
      quantityPerDay: line.quantity_per_day ?? "",
      dosePerBird: line.dose_per_bird ?? "",
      coverageWarning: "",
    });
  }
  return map;
}

export const makeRow = (overrides = {}) => ({
  id: nextId++,
  fromValue: 1,
  fromUnit: "Day",
  toValue: 1,
  toUnit: "Day",
  untilEnd: false,
  what: "",
  details: "",
  timeSlots: [],
  stockItemCode: null,
  // "fixed" → quantityPerDay units/day; "dose" → dosePerBird per live bird (× batch count).
  // Mutually exclusive — only the active mode's field is sent (see consumptionFields).
  consumptionMode: "fixed",
  quantityPerDay: "",
  dosePerBird: "",
  coverageWarning: "",
  ...overrides,
});
