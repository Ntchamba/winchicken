import { useCallback, useEffect, useState } from "react";
import { Check, Loader2 } from "lucide-react";
import { batchesApi } from "../api/endpoints";
import "../styles/protocol-edit-modal.css";
import { useDateDefaultingToToday } from "../hooks/useTodayISO";

function formatWeight(kg) {
  return `${kg} kg`;
}

/**
 * Dedicated weighing entry — own card, separate from the mortality/eggs `QuickEntryPanel`
 * (2026-08-25). Upserts only `DailyLog.avg_sample_weight` for a batch+date via the same
 * PUT /api/batches/{batchCode}/daily-logs/quick-entry/ endpoint `QuickEntryPanel` uses
 * (mortality/eggs sent as `null` — untouched), so a weighing never clobbers a mortality/eggs
 * entry already recorded for that date, and vice versa. Positioned directly below the growth
 * curves on both dashboard locations.
 *
 * @param {{batchCode: string, name: string, houseCode?: string, houseName?: string}[]} batches
 *   - More than one (global view) requires picking a batch before date/weight — the global
 *   view aggregates several active batches, so a weighing needs an explicit target, not a
 *   default. A single-item array (per-house view) hides the selector, implicitly scoped.
 * @param {() => void} [onLogged] - Called after a successful save (refetch the growth curve).
 */
export default function WeighingSection({ batches = [], onLogged }) {
  const isMulti = batches.length > 1;
  const [batchCode, setBatchCode] = useState("");
  const [date, setDate, today] = useDateDefaultingToToday();
  const [weight, setWeight] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const [recentByBatch, setRecentByBatch] = useState({});

  const batchCodesKey = batches.map((b) => b.batchCode || b.batch_code).join(",");
  const resolvedBatchCode = isMulti ? batchCode : (batches[0]?.batchCode || batches[0]?.batch_code || "");

  const loadRecent = useCallback(() => {
    if (!batchCodesKey) return;
    Promise.all(
      batches.map((b) => {
        const code = b.batchCode || b.batch_code;
        return batchesApi.dailyLogs(code).then(({ data }) => [code, data.results || data]);
      })
    ).then((pairs) => {
      const map = {};
      for (const [code, logs] of pairs) {
        map[code] = logs
          .filter((l) => l.avg_sample_weight != null)
          .sort((a, b) => b.log_date.localeCompare(a.log_date))
          .slice(0, 5);
      }
      setRecentByBatch(map);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchCodesKey]);

  useEffect(() => {
    loadRecent();
  }, [loadRecent]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!resolvedBatchCode || weight === "") return;
    setSaving(true);
    setSaved(false);
    setError("");
    try {
      await batchesApi.quickEntry(resolvedBatchCode, {
        date,
        mortality: null,
        eggsCollected: null,
        avgSampleWeight: Number(weight),
      });
      setSaved(true);
      setWeight("");
      loadRecent();
      onLogged?.();
    } catch (err) {
      setError(err.response?.data?.detail || "Impossible d'enregistrer la pesée.");
    } finally {
      setSaving(false);
    }
  };

  if (batches.length === 0) {
    return <p className="empty-state">Aucune bande active à peser.</p>;
  }

  return (
    <div className="card schedule-card weighing-section" style={{ marginBottom: 18 }}>
      <form onSubmit={handleSubmit}>
        <div className="quick-entry-row">
          {isMulti && (
            <label className="quick-entry-field">
              <span>Bâtiment / bande</span>
              <select value={batchCode} onChange={(e) => { setBatchCode(e.target.value); setSaved(false); }} required>
                <option value="" disabled>Choisir…</option>
                {batches.map((b) => {
                  const code = b.batchCode || b.batch_code;
                  return (
                    <option key={code} value={code}>
                      {(b.houseName ? `${b.houseName} — ` : "") + (b.name || b.batchName || code)}
                    </option>
                  );
                })}
              </select>
            </label>
          )}
          <label className="quick-entry-field">
            <span>Date de la pesée</span>
            <input type="date" value={date} max={today} onChange={(e) => { setDate(e.target.value); setSaved(false); }} />
          </label>
          <label className="quick-entry-field">
            <span>Poids moyen (kg)</span>
            <input
              type="number"
              min="0"
              step="0.001"
              placeholder="ex. 1.850"
              value={weight}
              onChange={(e) => { setWeight(e.target.value); setSaved(false); }}
              required
            />
          </label>
          {/* `padding:"0 18px"` used to override .save-button's base `13px 20px`, collapsing it
              to roughly a third of the onboarding wizard's "Suivant" button — same class, no
              override there. width:auto kept (this button sits in a row, not a full-width bar);
              padding override dropped so it gets the same "big primary action" scale (2026-08-26). */}
          <button type="submit" className="save-button" disabled={saving || !resolvedBatchCode} style={{ width: "auto" }}>
            {saving ? <Loader2 size={16} className="spin" /> : saved ? <Check size={16} /> : "Enregistrer"}
          </button>
        </div>
        {error && <p style={{ color: "var(--danger)", fontSize: 13, margin: "8px 0 0" }}>{error}</p>}
      </form>

      {isMulti ? (
        Object.entries(
          batches.reduce((byHouse, b) => {
            const houseKey = b.houseName || b.houseCode || "—";
            (byHouse[houseKey] ||= []).push(b);
            return byHouse;
          }, {})
        ).map(([houseName, houseBatches]) => {
          const entries = houseBatches.flatMap((b) => {
            const code = b.batchCode || b.batch_code;
            return (recentByBatch[code] || []).map((log) => ({ ...log, batchName: b.name || b.batchName || code }));
          }).sort((a, bb) => bb.log_date.localeCompare(a.log_date));
          if (entries.length === 0) return null;
          return (
            <div key={houseName} className="weighing-recent-group">
              <p className="weighing-recent-house">{houseName}</p>
              <ul className="weighing-recent-list">
                {entries.map((log) => (
                  <li key={log.id}>{log.log_date} — {formatWeight(log.avg_sample_weight)} <span>({log.batchName})</span></li>
                ))}
              </ul>
            </div>
          );
        })
      ) : (
        (() => {
          const code = batches[0].batchCode || batches[0].batch_code;
          const entries = recentByBatch[code] || [];
          if (entries.length === 0) return null;
          return (
            <ul className="weighing-recent-list" style={{ marginTop: 14, paddingTop: 12, borderTop: "1px solid var(--line)" }}>
              {entries.map((log) => (
                <li key={log.id}>{log.log_date} — {formatWeight(log.avg_sample_weight)}</li>
              ))}
            </ul>
          );
        })()
      )}
    </div>
  );
}
