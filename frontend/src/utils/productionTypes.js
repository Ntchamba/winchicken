// Mirrors apps.batches.models.ProductionType. The field has existed server-side since the
// first migration, but nothing ever asked the user for it — onboarding sent "BROILER"
// unconditionally — so this list is the first UI exposure of it.
export const PRODUCTION_TYPES = [
  { value: "BROILER", label: "Poulet de chair" },
  { value: "PULLET", label: "Poulette" },
  { value: "LAYER", label: "Pondeuse" },
];

export const productionTypeLabel = (value) =>
  PRODUCTION_TYPES.find((t) => t.value === value)?.label || value;
