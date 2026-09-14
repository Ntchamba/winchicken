// Shared French label maps for the Finances single-page view (2026-08-27, Finances restructure).
// Kept separate from GlobaleSection's own combined transactions-table map (which mixes both
// axes for one raw `row.category` value) since Ventes/Achats only ever need one axis each.
export const PRODUCT_TYPE_LABELS = {
  BIRD: "Poulet", EGG: "Œuf", CULL: "Réforme", MANURE: "Fumier",
};

export const EXPENSE_CATEGORY_LABELS = {
  FEED: "Aliment", VETERINARY: "Vétérinaire", MISC: "Divers", DEPRECIATION: "Amortissement", LABOR: "Main-d'œuvre",
};

export const PERIOD_OPTIONS = [
  { value: "week", label: "Semaine" },
  { value: "month", label: "Mois" },
  { value: "year", label: "Année" },
];
