import { useState } from "react";
import { Check, Loader2, RotateCcw } from "lucide-react";
import { tasksApi } from "../api/endpoints";
import { getServerErrorMessage } from "../api/errors";
import "./task-complete-button.css";

/**
 * "Marquer comme fait" / "Annuler" for one protocol-task occurrence.
 *
 * Shared by the worker's "Mes tâches" list and the per-house panel so the two can't drift —
 * completing from either place hits the same endpoint and deducts stock the same way.
 *
 * Insufficient stock is a confirmation, not a refusal: the server returns the shortfall and
 * writes nothing, we show what is missing, and the user decides. A farm that sourced feed
 * elsewhere still needs to record the work as done; the resulting negative balance is the
 * signal to reconcile, which is better than refusing to record reality.
 *
 * @param {string} houseCode
 * @param {string} taskId - the ProtocolTemplate id, as `compute_tasks_now` emits it.
 * @param {boolean} done
 * @param {?string} completedByName
 * @param {() => void} onChanged - called after a successful complete/undo so the caller refetches.
 */
export default function TaskCompleteButton({ houseCode, taskId, done, completedByName, onChanged }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [shortfall, setShortfall] = useState(null);

  const run = async (fn) => {
    setBusy(true);
    setError("");
    try {
      await fn();
      setShortfall(null);
      onChanged?.();
    } catch (err) {
      setError(getServerErrorMessage(err, "Action impossible pour le moment."));
    } finally {
      setBusy(false);
    }
  };

  const complete = (force = false) => run(async () => {
    const { data } = await tasksApi.complete(houseCode, taskId, { force });
    if (data.status === "insufficient_stock") {
      setShortfall(data.shortfall);
      throw new Error("__shortfall__");  // keeps the catch from clearing it
    }
  }).catch(() => {});

  const undo = () => run(() => tasksApi.uncomplete(houseCode, taskId));

  if (done) {
    return (
      <div className="task-complete">
        <span className="task-done-badge">
          <Check size={14} strokeWidth={2.6} />
          Fait{completedByName ? ` — ${completedByName}` : ""}
        </span>
        <button type="button" className="task-undo-button" onClick={undo} disabled={busy}>
          {busy ? <Loader2 size={14} className="spin" /> : <RotateCcw size={14} strokeWidth={2.2} />}
          Annuler
        </button>
        {error && <p className="field-error task-complete-error">{error}</p>}
      </div>
    );
  }

  return (
    <div className="task-complete">
      <button type="button" className="task-done-button" onClick={() => complete(false)} disabled={busy}>
        {busy ? <Loader2 size={15} className="spin" /> : <Check size={15} strokeWidth={2.6} />}
        Marquer comme fait
      </button>

      {shortfall && (
        <div className="task-shortfall" role="alert">
          <p>
            Stock insuffisant : <strong>{shortfall.itemName}</strong> — il en faut{" "}
            {shortfall.needed} {shortfall.unit}, il en reste {shortfall.onHand} {shortfall.unit}.
          </p>
          <div className="task-shortfall-actions">
            <button type="button" className="task-undo-button" onClick={() => setShortfall(null)} disabled={busy}>
              Annuler
            </button>
            <button type="button" className="task-done-button" onClick={() => complete(true)} disabled={busy}>
              Valider quand même
            </button>
          </div>
        </div>
      )}

      {error && <p className="field-error task-complete-error">{error}</p>}
    </div>
  );
}
