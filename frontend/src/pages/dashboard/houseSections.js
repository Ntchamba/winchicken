import { AlertTriangle, ClipboardCheck, Scale, TrendingUp, Warehouse } from "lucide-react";

/**
 * The house view's destinations, in display order. One list feeds both the hub's branches
 * (HouseDetailPage) and the cross-links row (HouseLayout -> QuickLinksBar), so the two can
 * never offer a different set. `path` is relative to `/dashboard/houses/:houseCode`.
 */
export const HOUSE_SECTIONS = [
  { key: "cases", path: "cases", label: "Cas signalés", Icon: AlertTriangle },
  { key: "evolution", path: "evolution", label: "Évolution", Icon: TrendingUp },
  { key: "tasks", path: "tasks", label: "Tâches", Icon: ClipboardCheck },
  { key: "weighing", path: "weighing", label: "Pesée", Icon: Scale },
];

export const houseBasePath = (houseCode) => `/dashboard/houses/${houseCode}`;

/** Cross-links row: the hub itself first, then every destination. */
export function houseCrossLinks(houseCode) {
  const base = houseBasePath(houseCode);
  return [
    { to: base, label: "Vue du bâtiment", Icon: Warehouse },
    ...HOUSE_SECTIONS.map(({ path, label, Icon }) => ({ to: `${base}/${path}`, label, Icon })),
  ];
}
