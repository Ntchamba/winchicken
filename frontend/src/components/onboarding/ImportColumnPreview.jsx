import { AlertTriangle, ArrowRight, Check, CircleHelp, Wand2 } from "lucide-react";
import "../../pages/onboarding/batch-flow.css";

// How each mapping method is presented. `method` comes from the server's matcher
// (apps/core/column_matching.py) — exact | fuzzy | default | missing.
const METHOD = {
  exact: { label: "Reconnue", Icon: Check, tone: "ok" },
  fuzzy: { label: "Approximative", Icon: Wand2, tone: "warn" },
  default: { label: "Valeur par défaut", Icon: CircleHelp, tone: "muted" },
  missing: { label: "À vérifier", Icon: AlertTriangle, tone: "bad" },
};

/**
 * What the file's columns were understood to mean, shown before anything is imported.
 *
 * The mapping is done server-side by a fixed synonym table plus edit distance — no guessing
 * that the user can't see. Approximate (fuzzy) matches are called out on purpose: they are the
 * ones worth a second look, since a close-but-wrong header is the failure mode that a purely
 * automatic remapping would hide.
 *
 * @param {Object} columns - The server's `columns` report: `{ matches, unknownHeaders, unresolved }`.
 * @param {number} rowCount
 * @param {Object[]} [skipped] - Per-row skip report `[{line, reason}]`.
 * @param {() => void} onConfirm - Disabled while any required column is unresolved.
 * @param {() => void} onCancel
 * @param {boolean} [busy]
 */
export default function ImportColumnPreview({ columns, rowCount, skipped = [], onConfirm, onCancel, busy = false }) {
  const matches = columns?.matches || [];
  const unresolved = columns?.unresolved || [];
  const unknown = columns?.unknownHeaders || [];
  const blocked = unresolved.length > 0;

  return (
    <div className="import-preview">
      <h3 className="import-preview-title">Vérifiez les colonnes reconnues</h3>
      <p className="batch-choice-hint">
        Vos en-têtes ont été rapprochés des colonnes attendues. Rien n'est importé tant que vous
        n'avez pas confirmé.
      </p>

      <ul className="import-preview-list">
        {matches.map((m) => {
          const meta = METHOD[m.method] || METHOD.missing;
          const { Icon } = meta;
          return (
            <li key={m.key} className={`import-preview-row import-preview-row--${meta.tone}`}>
              <span className="import-preview-icon"><Icon size={15} strokeWidth={2.2} /></span>
              <span className="import-preview-mapping">
                {m.header ? (
                  <>
                    <strong>{m.header}</strong>
                    <ArrowRight size={13} strokeWidth={2.2} className="import-preview-arrow" />
                    <span>{m.label}</span>
                  </>
                ) : (
                  <span>{m.label}{m.required ? " (obligatoire)" : ""}</span>
                )}
              </span>
              <span className="import-preview-method">
                {meta.label}
                {m.method === "fuzzy" && ` · ${Math.round(m.confidence * 100)} %`}
              </span>
              {m.note && <span className="import-preview-note">{m.note}</span>}
            </li>
          );
        })}
      </ul>

      {unknown.length > 0 && (
        <p className="import-preview-note import-preview-unknown">
          Colonnes du fichier non utilisées : {unknown.map((h) => `« ${h} »`).join(", ")}.
        </p>
      )}

      {blocked ? (
        <p className="batch-import-summary batch-import-summary--warn">
          <strong>
            Colonne{unresolved.length > 1 ? "s" : ""} obligatoire{unresolved.length > 1 ? "s" : ""} introuvable
            {unresolved.length > 1 ? "s" : ""} : {unresolved.map((u) => `« ${u} »`).join(", ")}.
          </strong>
          <span style={{ display: "block", marginTop: 4 }}>
            Renommez cette colonne dans votre fichier (ou repartez du modèle), puis réimportez-le.
          </span>
        </p>
      ) : (
        <p className={`batch-import-summary ${skipped.length ? "batch-import-summary--warn" : "batch-import-summary--ok"}`}>
          <strong>
            {rowCount} ligne{rowCount > 1 ? "s" : ""} prête{rowCount > 1 ? "s" : ""} à importer
            {skipped.length > 0 && `, ${skipped.length} ignorée${skipped.length > 1 ? "s" : ""}`}.
          </strong>
          {skipped.length > 0 && (
            <span style={{ display: "block", marginTop: 4 }}>
              {skipped.map((s) => `Ligne ${s.line} : ${s.reason}`).join(" · ")}
            </span>
          )}
        </p>
      )}

      <div className="batch-step-actions">
        <button type="button" className="batch-back-button" onClick={onCancel} disabled={busy}>
          Annuler
        </button>
        <button
          type="button"
          className="add-button batch-step-next"
          onClick={onConfirm}
          disabled={blocked || busy || rowCount === 0}
        >
          Confirmer l'import
        </button>
      </div>
    </div>
  );
}
