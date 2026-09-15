import { useState } from "react";
import { Check, Loader2 } from "lucide-react";
import { batchesApi } from "../api/endpoints";
import "../styles/protocol-edit-modal.css";
import { useDateDefaultingToToday } from "../hooks/useTodayISO";

// "Signal de perte" severity (2026-08-25 bugfix — this used to be a plain small number input
// with no visual weight at all): gray at 0, amber for any non-zero count while we don't yet
// know how it affects the batch's cumulative mortality (before save, or the batch has none of
// its own — a single-item `batches` array without `initialCount`), red once the *cumulative*
// mortality (returned by the quick-entry endpoint, not recomputed here) exceeds the batch's
// unfavorable reference bound.
function severityFor(mortalityValue, cumulativePct, referenceRange) {
  const count = Number(mortalityValue) || 0;
  if (count === 0) return "neutral";
  if (cumulativePct != null && referenceRange && cumulativePct > referenceRange[1]) return "danger";
  return "warning";
}

/**
 * Light day-to-day entry panel — mortality and eggs collected, upserted into DailyLog via
 * PUT /api/batches/{batchCode}/daily-logs/quick-entry/. The date field applies to the whole
 * submission (any past date, not just today) so a correction or backdated entry doesn't have
 * to be forced onto today. Both value fields are independently optional: each is sent as `null`
 * when left blank, which the backend treats as "don't touch this field" — logging mortality
 * doesn't blank out eggs already recorded for that date, and vice versa. Average weight
 * (2026-08-25) lives in its own `WeighingSection` component, not here — this panel only ever
 * touches mortality/eggs, same as before that field existed.
 *
 * @param {{batchCode: string, name: string}[]} batches - Batches this panel can log against.
 *   A single-item array (per-house view, pre-scoped) hides the selector; more than one
 *   (global view) shows a dropdown.
 * @param {() => void} [onLogged] - Called after a successful save, so the caller can refetch
 *   whatever depends on DailyLog.
 */
export default function QuickEntryPanel({ batches = [], onLogged }) {
  const [batchCode, setBatchCode] = useState(batches[0]?.batch_code || batches[0]?.batchCode || "");
  const [date, setDate, today] = useDateDefaultingToToday();
  const [mortality, setMortality] = useState("");
  const [eggsCollected, setEggsCollected] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const [lastResult, setLastResult] = useState(null); // {mortality, cumulativeMortalityPct, mortalityReferenceRange}

  const resolvedBatchCode = batchCode || batches[0]?.batch_code || batches[0]?.batchCode || "";

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!resolvedBatchCode) return;
    setSaving(true);
    setSaved(false);
    setError("");
    try {
      const { data } = await batchesApi.quickEntry(resolvedBatchCode, {
        date,
        mortality: mortality === "" ? null : Number(mortality),
        eggsCollected: eggsCollected === "" ? null : Number(eggsCollected),
      });
      setSaved(true);
      setLastResult(data);
      setMortality("");
      setEggsCollected("");
      onLogged?.();
    } catch (err) {
      setError(err.response?.data?.detail || "Impossible d'enregistrer.");
    } finally {
      setSaving(false);
    }
  };

  if (batches.length === 0) {
    return <p className="empty-state">Aucune bande active à renseigner.</p>;
  }

  const liveSeverity = severityFor(mortality, lastResult?.cumulativeMortalityPct, lastResult?.mortalityReferenceRange);

  return (
    <form className="card schedule-card quick-entry-form" onSubmit={handleSubmit}>
      <div className="quick-entry-row">
        {batches.length > 1 && (
          <label className="quick-entry-field">
            <span>Bande</span>
            <select value={resolvedBatchCode} onChange={(e) => { setBatchCode(e.target.value); setSaved(false); }}>
              {batches.map((b) => (
                <option key={b.batch_code || b.batchCode} value={b.batch_code || b.batchCode}>
                  {b.name || b.batchName || b.batch_code || b.batchCode}
                </option>
              ))}
            </select>
          </label>
        )}
        <label className="quick-entry-field">
          <span>Date</span>
          <input type="date" value={date} max={today} onChange={(e) => { setDate(e.target.value); setSaved(false); }} />
        </label>
        <label className="quick-entry-field">
          <span>Mortalité — signal de perte</span>
          <input
            className={`mortality-input mortality-${liveSeverity}`}
            type="number"
            min="0"
            placeholder="0"
            value={mortality}
            onChange={(e) => { setMortality(e.target.value); setSaved(false); }}
          />
        </label>
        <label className="quick-entry-field">
          <span>Œufs collectés</span>
          <input type="number" min="0" placeholder="0" value={eggsCollected} onChange={(e) => { setEggsCollected(e.target.value); setSaved(false); }} />
        </label>
        {/* Same fix as WeighingSection's Enregistrer (2026-08-26): dropped the `padding:"0
            18px"` override so this gets .save-button's full base scale, matching the
            onboarding wizard's "Suivant". */}
        <button type="submit" className="save-button" disabled={saving} style={{ width: "auto" }}>
          {saving ? <Loader2 size={16} className="spin" /> : saved ? <Check size={16} /> : "Enregistrer"}
        </button>
      </div>
      {saved && lastResult && (
        <p className={`mortality-summary mortality-summary-${severityFor(lastResult.mortality, lastResult.cumulativeMortalityPct, lastResult.mortalityReferenceRange)}`}>
          {lastResult.mortality} perte{lastResult.mortality === 1 ? "" : "s"} enregistrée{lastResult.mortality === 1 ? "" : "s"} aujourd'hui
          {lastResult.cumulativeMortalityPct != null && (
            <> · mortalité cumulée {lastResult.cumulativeMortalityPct}% (référence {lastResult.mortalityReferenceRange[0]}-{lastResult.mortalityReferenceRange[1]}%)</>
          )}
        </p>
      )}
      {error && <p style={{ color: "var(--danger)", fontSize: 13, margin: "8px 0 0" }}>{error}</p>}
    </form>
  );
}
