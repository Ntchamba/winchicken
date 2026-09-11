import { useRef } from "react";
import { Download, FileSpreadsheet, Loader2 } from "lucide-react";
import "../../pages/onboarding/batch-flow.css";

/**
 * One import type on the Excel screen: a template download plus a file picker. Same controls
 * (and the same `.add-button` styling, `.xlsx`-only picker, hidden input) as the import
 * buttons already in `HouseProtocolForm` and `StockParametersModal` — this only groups them
 * into a card so several import types can sit side by side.
 *
 * @param {string} title
 * @param {string} hint - One line on what the file should contain.
 * @param {?string} templateUrl - Omitted for a type with no template yet.
 * @param {(file: File) => void} [onImport] - Receives the picked file. Ignored when disabled.
 * @param {boolean} [importing] - Shows a spinner and blocks a second pick.
 * @param {boolean} [disabled] - Renders the card inert (used for the not-yet-built Finances import).
 * @param {?string} [badge] - Small pill next to the title, e.g. "Bientôt disponible".
 * @param {React.ReactNode} [children] - Result/summary block, rendered under the actions.
 * @param {?string} [errorMessage]
 */
export default function ExcelImportCard({
  title, hint, templateUrl, onImport, importing = false, disabled = false, badge = null, children, errorMessage = null,
}) {
  const inputRef = useRef(null);

  const pick = (e) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // let the same file be picked again
    if (file) onImport?.(file);
  };

  return (
    <div className={`batch-import-card${disabled ? " batch-import-card--disabled" : ""}`}>
      <div className="batch-import-head">
        <span className="batch-import-name">{title}</span>
        {badge && <span className="batch-import-badge">{badge}</span>}
      </div>
      <p className="batch-choice-hint">{hint}</p>

      <div className="batch-import-actions">
        {templateUrl && !disabled && (
          <a className="add-button" style={{ marginTop: 0, textDecoration: "none" }} href={templateUrl}>
            <Download size={14} strokeWidth={2.2} />
            Télécharger un modèle
          </a>
        )}
        <button
          type="button"
          className="add-button"
          style={{ marginTop: 0 }}
          onClick={() => inputRef.current?.click()}
          disabled={disabled || importing}
        >
          {importing ? <Loader2 size={14} className="spin" /> : <FileSpreadsheet size={14} strokeWidth={2.2} />}
          Importer un fichier
        </button>
        {!disabled && (
          <input ref={inputRef} type="file" accept=".xlsx" onChange={pick} style={{ display: "none" }} />
        )}
      </div>

      {errorMessage && <p className="field-error" style={{ margin: 0 }}>{errorMessage}</p>}
      {children}
    </div>
  );
}
