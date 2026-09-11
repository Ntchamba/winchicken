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
