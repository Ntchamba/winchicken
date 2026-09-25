import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, X } from "lucide-react";
import { batchesApi } from "../api/endpoints";
import UnusualCaseReportForm from "./UnusualCaseReportForm";

/**
 * Sidebar-wide "Signaler un cas" shortcut (2026-08-26) — its own visually separated, warning-
 * toned button/card (not just another nav link), matching the "bigger, more visible" treatment
 * `UnusualCaseReportForm`'s own button already got on 2026-08-26 (see that component's
 * docstring: amber/`--warning`-adjacent framing for an alert-worthy action, not destructive
 * like a delete button). Picks a house — and its active batch — since this is reachable from
 * anywhere, not scoped to a house already like `UnusualCaseReportForm`'s existing
 * `HouseDetailPage` call site. Reuses that form as-is (`startOpen` skips its own collapsed
 * state so this stays a one-house-pick-then-fill flow, not house-pick-then-reveal-then-fill).
 *
 * @param {{houseCode: string, name: string}[]} houses
 * @param {number} [openCasesCount] - Unresolved-case badge (2026-08-27, Part B pulse treatment)
 *   — hidden entirely at 0, matching the other sidebar badges (Stock/Finance).
 */
export default function IncidentShortcut({ houses, openCasesCount = 0 }) {
  const [open, setOpen] = useState(false);
  const [houseCode, setHouseCode] = useState("");
  // undefined = not looked up yet for the current houseCode, null = looked up, none ACTIVE.
  const [activeBatch, setActiveBatch] = useState(undefined);
  const [reported, setReported] = useState(false);

  useEffect(() => {
    if (!houseCode) {
      setActiveBatch(undefined);
      return;
    }
    setActiveBatch(undefined);
    batchesApi.list(houseCode).then(({ data }) => {
      const batches = data.results || data;
      setActiveBatch(batches.find((b) => b.status === "ACTIVE") || null);
    });
  }, [houseCode]);

  const reset = () => {
    setOpen(false);
    setHouseCode("");
    setActiveBatch(undefined);
    setReported(false);
  };

  return (
    <>
      <button className="incident-shortcut" onClick={() => setOpen(true)}>
        <AlertTriangle size={16} strokeWidth={2} />
        Signaler un cas
        {openCasesCount > 0 && <span className="sidebar-link-badge danger pulse-alert">{openCasesCount > 9 ? "9+" : openCasesCount}</span>}
      </button>

      {/* Portalled to <body>: the sidebar is position:sticky, a stacking context of its own, so a
          modal rendered inside it sat under the page content whatever its z-index — the task
          cards showed through "Enregistrer mes heures" (campaign 3, in the browser). */}
      {open && createPortal(
        <div
          style={{
            position: "fixed", inset: 0, zIndex: 70, display: "flex",
            alignItems: "center", justifyContent: "center", background: "rgba(0,0,0,.4)",
          }}
        >
          <div className="card schedule-card" style={{ width: 360, maxWidth: "90vw" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
              <h2 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: "#10242c" }}>Signaler un cas</h2>
              <button
                onClick={reset}
                aria-label="Fermer"
                style={{ border: 0, background: "none", color: "var(--muted)", cursor: "pointer", padding: 0, display: "grid", placeItems: "center", minWidth: 44, minHeight: 44, marginRight: -12 }}
              >
                <X size={18} />
              </button>
            </div>

            {reported ? (
              <>
                <p style={{ fontSize: 13.5, color: "var(--muted)" }}>Signalement envoyé. Merci.</p>
                <button className="save-button" style={{ width: "100%", marginTop: 10 }} onClick={reset}>
                  Fermer
                </button>
              </>
            ) : (
              <>
                <label className="field" style={{ marginBottom: 12 }}>
                  <span>Bâtiment</span>
                  <select value={houseCode} onChange={(e) => setHouseCode(e.target.value)}>
                    <option value="">Sélectionner…</option>
                    {houses.map((h) => (
                      <option key={h.houseCode} value={h.houseCode}>
                        {h.name}
                      </option>
                    ))}
                  </select>
                </label>

                {houseCode && activeBatch === undefined && (
                  <p style={{ fontSize: 13, color: "var(--muted)" }}>Chargement…</p>
                )}
                {houseCode && activeBatch === null && (
                  <p style={{ fontSize: 13, color: "var(--muted)" }}>Aucune bande active dans ce bâtiment.</p>
                )}
                {activeBatch && (
                  <UnusualCaseReportForm
                    batchCode={activeBatch.batch_code}
                    startOpen
                    onReported={() => setReported(true)}
                  />
                )}
              </>
            )}
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
