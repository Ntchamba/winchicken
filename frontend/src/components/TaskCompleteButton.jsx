import { useState } from "react";
import { Check, Loader2, RotateCcw } from "lucide-react";
import { tasksApi } from "../api/endpoints";
import { getServerErrorMessage } from "../api/errors";
import { useAuth } from "../context/AuthContext";
import "./task-complete-button.css";

/**
 * "Marquer comme fait" / "Annuler" for one protocol-task occurrence.
 *
 * Shared by the worker's "Mes tâches" list and the per-house panel so the two can't drift —
 * completing from either place hits the same endpoint and deducts stock the same way.
 *
 * Shared completion (FIX 7): a line can carry several assignees and the occurrence is keyed on
 * `(line, batch, date, time_slot)`, never on the assignee — so the first worker to mark it done
 * closes it for everyone and the stock moves exactly once. The badge therefore has to name the
 * completer: the other assignees see a row they did not touch reading as finished, and "Fait"
 * alone would look like their own screen lying to them. Undo stays open to any of them, for the
 * same reason completing is: on the ground they are doing one job, not three.
 *
 * Insufficient stock is a confirmation, not a refusal: the server returns the shortfall and
 * writes nothing, we show what is missing, and the user decides. A farm that sourced feed
 * elsewhere still needs to record the work as done; the resulting negative balance is the
 * signal to reconcile, which is better than refusing to record reality.
 *
 * @param {string} houseCode
 * @param {string} taskId - the ProtocolTemplate id, as `compute_tasks_now` emits it.
 * @param {?number} timeSlotId - which occurrence of a multi-slot line this row is (a
 *   twice-daily feeding line renders two rows, each completable and deductible on its own).
 *   Null for a line with no time slots.
 * @param {boolean} done
 * @param {?number} completedBy - id of whoever closed it; compared against the logged-in user
 *   rather than the name, so two workers who share a first name never read as each other.
 * @param {?string} completedByName
 * @param {() => void} onChanged - called after a successful complete/undo so the caller refetches.
 */
export default function TaskCompleteButton({
  houseCode, taskId, timeSlotId = null, done, completedBy = null, completedByName, onChanged,
}) {
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [shortfall, setShortfall] = useState(null);

  /**
   * Runs one action with the busy/error bookkeeping. `fn` may return `{ halted: true }` for an
   * outcome that is neither success nor failure — today only the shortfall confirmation, which
   * has just opened its own panel and must keep it.
   *
   * A halt must never reach the catch. `getServerErrorMessage` reads a missing `err.response`
   * as "the request never got to the server", so signalling the shortfall by throwing made a
   * 200 render as "Le serveur est inaccessible" underneath the panel — the exact ambiguity
   * api/errors.js exists to remove, and the one that hid the Part B outage.
   */
  const run = async (fn) => {
    setBusy(true);
    setError("");
    try {
      const result = await fn();
      if (result?.halted) return;
      setShortfall(null);
      onChanged?.();
    } catch (err) {
      setError(getServerErrorMessage(err, "Action impossible pour le moment."));
    } finally {
      setBusy(false);
    }
  };

  const complete = (force = false) => run(async () => {
    const { data } = await tasksApi.complete(houseCode, taskId, { force, timeSlotId });
    if (data.status === "insufficient_stock") {
      setShortfall(data.shortfall);
      return { halted: true };
    }
    return null;
  });

  const undo = () => run(() => tasksApi.uncomplete(houseCode, taskId, { timeSlotId }));

  // Clears the error as well as the panel: whatever it said belonged to the attempt the user
  // is walking away from, and a stale line under a dismissed panel reads as a fresh failure.
  const dismissShortfall = () => {
    setShortfall(null);
    setError("");
  };

  if (done) {
    return (
      <div className="task-complete">
        <span className="task-done-badge">
          <Check size={14} strokeWidth={2.6} />
          {completedBy != null && completedBy === user?.id
            ? "Fait par vous"
            : completedByName ? `Fait par ${completedByName}` : "Fait"}
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
            <button type="button" className="task-undo-button" onClick={dismissShortfall} disabled={busy}>
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
