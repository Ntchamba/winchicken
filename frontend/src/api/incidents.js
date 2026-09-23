import { maintenanceApi } from "./endpoints";

// Reads either a paginated envelope's `count` or a plain array's `length` — the same
// `data.results || data` uncertainty every other list consumer in this app already handles,
// just reduced to a number instead of an array.
export function countOf(data) {
  return typeof data.count === "number" ? data.count : (data.results || data).length;
}

/**
 * Open incidents = unresolved `UnusualCase` + OPEN `EquipmentFault` — the same two queries
 * `IncidentsPanel` lists, so every count shown for "Cas signalés" (sidebar badge, house hub)
 * agrees with the list itself. No backend count endpoint exists for this pair.
 *
 * @param {string} [houseCode] - Omit for farm-wide.
 * @returns {Promise<number>}
 */
export async function countOpenIncidents(houseCode) {
  const scope = houseCode ? { house_code: houseCode } : {};
  const [casesRes, faultsRes] = await Promise.all([
    maintenanceApi.cases({ ...scope, resolved: "false" }),
    maintenanceApi.faults({ ...scope, status: "OPEN" }),
  ]);
  return countOf(casesRes.data) + countOf(faultsRes.data);
}
