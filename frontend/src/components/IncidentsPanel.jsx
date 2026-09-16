import { useEffect, useState } from "react";
import { AlertTriangle, Check, ChevronDown, ChevronUp, History, Loader2, Wrench } from "lucide-react";
import { maintenanceApi } from "../api/endpoints";

const DESCRIPTION_CLAMP = 120;

// case_date/reported_date are plain DateFields (no time-of-day stored anywhere on either
// model) — day-level precision is the best this data actually supports, not the finer-grained
// "time since reported" the task's own wording implied.
function daysAgoLabel(isoDate) {
  const diffDays = Math.floor((Date.now() - new Date(`${isoDate}T00:00:00`).getTime()) / 86400000);
  if (diffDays <= 0) return "Aujourd'hui";
  if (diffDays === 1) return "Il y a 1 jour";
  return `Il y a ${diffDays} jours`;
}

/**
 * "Cas signalés" — prominent, color-coded open-incidents panel (2026-08-26, docs/
 * deviations.md Part 16, Part D). Reused as-is on both the global view (`houseCode` omitted —
 * farm-wide) and the per-house view (`houseCode` set) per the task's own instruction that the
 * per-house version stay "consistent styling... just filtered" — literally the same component,
 * not a styled-alike copy.
 *
 * Merges two sources — `GET /api/unusual-cases/?resolved=false` and `GET
 * /api/equipment-faults/?status=OPEN` (both farm-scoped server-side, additionally
 * `?house_code=`-filtered when `houseCode` is given) — into one list, newest first. No photo
 * field exists on either `UnusualCase` or `EquipmentFault` anywhere in this codebase (checked
 * before assuming the task's "photo if one was attached" premise was real) — omitted rather
 * than fabricated.
 *
 * Resolving (`POST .../resolve/`, reserved server-side to the appropriate role per model — see
 * `apps.maintenance.views`) refetches both lists, so a resolved item disappears from this view
 * immediately; the row itself is never deleted, only its `resolved`/`status` flips — it stays
 * in the database (and in `/dashboard/audit`, since both resolve actions call
 * `record_audit_log`).
 *
 * "Historique" tab (2026-08-27, Feature 5, docs/deviations.md) — a second tab in the same
 * panel/component (rather than a separate route) so the global/per-house reuse this task
 * inherited stays free: switches the same two list calls to `resolved=true`/`status=RESOLVED`
 * and renders read-only cards (who resolved it + when, in place of the Résolu button) instead
 * of a second, separately-maintained view.
 *
 * @param {string} [houseCode] - Omit for farm-wide (global view); set to scope to one house.
 * @param {number} [reloadKey] - Bump to refetch after a case was reported elsewhere on the page
 *   (2026-09-16, FIX 8 group 2) — same shape as `AssignmentsPanel`'s, so a freshly reported
 *   case shows up here instead of leaving the list looking unchanged.
 */
export default function IncidentsPanel({ houseCode, reloadKey }) {
  const [tab, setTab] = useState("open");
  const [cases, setCases] = useState([]);
  const [faults, setFaults] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [resolvingId, setResolvingId] = useState(null);

  const load = () => {
    const scope = houseCode ? { house_code: houseCode } : {};
    const open = tab === "open";
    setLoaded(false);
    Promise.all([
      maintenanceApi.cases({ ...scope, resolved: open ? "false" : "true" }),
      maintenanceApi.faults({ ...scope, status: open ? "OPEN" : "RESOLVED" }),
    ]).then(([casesRes, faultsRes]) => {
      setCases(casesRes.data.results || casesRes.data);
      setFaults(faultsRes.data.results || faultsRes.data);
      setLoaded(true);
    });
  };

  useEffect(() => { load(); }, [houseCode, tab, reloadKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const items = [
    ...cases.map((c) => ({
      id: `case-${c.case_code}`, kind: 'case', label: 'Cas particulier',
      houseName: c.houseName, batchName: c.batchName, description: c.case_description,
      reporterName: c.reporterName, date: c.case_date,
      // resolved_at is a full ISO datetime (unlike every other date field here, which are all
      // plain dates) — sliced to "YYYY-MM-DD" so it works with daysAgoLabel's own
      // `${isoDate}T00:00:00` construction below instead of double-appending a time part.
      resolvedByName: c.resolvedByName, resolvedAt: c.resolved_at ? c.resolved_at.slice(0, 10) : null,
      resolve: () => maintenanceApi.resolveCase(c.case_code),
    })),
    ...faults.map((f) => ({
      id: `fault-${f.fault_code}`, kind: 'fault', label: "Panne d'équipement",
      houseName: f.houseName, batchName: null, description: f.fault_description,
      reporterName: f.technicianName, date: f.reported_date,
      resolvedByName: f.resolvedByName, resolvedAt: f.repaired_date,
      resolve: () => maintenanceApi.resolveFault(f.fault_code),
    })),
  ].sort((a, b) => new Date(b.date) - new Date(a.date));

  const handleResolve = async (item) => {
    setResolvingId(item.id);
    try {
      await item.resolve();
      load();
    } finally {
      setResolvingId(null);
    }
  };

  return (
    <div className="incidents-panel">
      <div className="incidents-panel-header">
        <h2>
          <AlertTriangle size={18} strokeWidth={2} className={tab === "open" && items.length > 0 ? "pulse-alert" : ""} />
          {" "}Cas signalés
        </h2>
        {tab === "open" && items.length > 0 && (
          <span className="incidents-count-badge pulse-alert">{items.length} cas ouvert{items.length > 1 ? "s" : ""}</span>
        )}
      </div>

      <div className="incidents-tabs">
        <button
          type="button"
          className={`incidents-tab ${tab === "open" ? "active" : ""}`}
          onClick={() => setTab("open")}
        >
          <AlertTriangle size={13} strokeWidth={2} /> Cas signalés
        </button>
        <button
          type="button"
          className={`incidents-tab ${tab === "history" ? "active" : ""}`}
          onClick={() => setTab("history")}
        >
          <History size={13} strokeWidth={2} /> Historique
        </button>
      </div>

      {!loaded ? (
        <p className="empty-state">Chargement…</p>
      ) : items.length === 0 ? (
        <p className="empty-state">{tab === "open" ? "Aucun cas signalé ouvert." : "Aucun cas résolu pour le moment."}</p>
      ) : (
        <div className="incidents-list">
          {items.map((item) => {
            const expanded = expandedId === item.id;
            const Icon = item.kind === 'fault' ? Wrench : AlertTriangle;
            return (
              <div key={item.id} className={`incident-card incident-${item.kind}`}>
                <span className="incident-icon"><Icon size={18} strokeWidth={1.8} /></span>
                <div className="incident-body">
                  <div className="incident-top-row">
                    <p className="incident-title">
                      {item.label} — {item.houseName}{item.batchName ? ` · ${item.batchName}` : ""}
                    </p>
                    <span className="incident-time">{daysAgoLabel(item.date)}</span>
                  </div>
                  <p className={expanded ? "incident-description" : "incident-description incident-description-clamped"}>
                    {item.description}
                  </p>
                  {item.description?.length > DESCRIPTION_CLAMP && (
                    <button className="incident-expand" onClick={() => setExpandedId(expanded ? null : item.id)}>
                      {expanded ? <>Réduire <ChevronUp size={13} /></> : <>Voir plus <ChevronDown size={13} /></>}
                    </button>
                  )}
                  {item.reporterName && <p className="incident-reporter">Signalé par {item.reporterName}</p>}
                  {tab === "history" && item.resolvedByName && (
                    <p className="incident-reporter">Résolu par {item.resolvedByName}{item.resolvedAt ? ` — ${daysAgoLabel(item.resolvedAt)}` : ""}</p>
                  )}
                </div>
                {tab === "open" && (
                  <button
                    className="incident-resolve-button"
                    disabled={resolvingId === item.id}
                    onClick={() => handleResolve(item)}
                  >
                    {resolvingId === item.id ? <Loader2 size={14} className="spin" /> : <Check size={14} strokeWidth={2.2} />}
                    Résolu
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
