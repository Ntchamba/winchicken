import { useState } from "react";
import { PRODUCTION_TYPES } from "../../utils/productionTypes";
import "../../pages/onboarding/batch-flow.css";

/**
 * First step of batch creation: the handful of fields that identify the batch, asked before
 * the user picks how to fill the protocol (manually or from an Excel file).
 *
 * The fields themselves are not new — `HouseProtocolForm` has always carried them in its own
 * header, and still does (this step seeds them via its `initialHeader` prop, it does not
 * replace them). What is new is `productionType`: `PoultryBatch.production_type` has existed
 * server-side all along with BROILER/LAYER, but no screen ever asked, so onboarding hardcoded
 * "BROILER". Broiler stays the default here, so a user who ignores the selector gets exactly
 * the previous behavior.
 *
 * @param {Object} [initial] - Values to re-open with, so stepping back loses nothing.
 * @param {(header: Object) => void} onNext - Receives the header, including `productionType`.
 * @param {string} [title] - Heading override.
 */
export default function BatchHeaderStep({ initial = {}, onNext, title = "Nouvelle bande" }) {
  const [batchName, setBatchName] = useState(initial.batchName || "");
  const [buildingName, setBuildingName] = useState(initial.buildingName || "");
  const [chicksPlaced, setChicksPlaced] = useState(initial.chicksPlaced ?? "");
  const [productionType, setProductionType] = useState(initial.productionType || "BROILER");

  const complete = batchName.trim() && String(chicksPlaced).trim() && buildingName.trim();

  const submit = (e) => {
    e.preventDefault();
    if (!complete) return;
    onNext({ ...initial, batchName: batchName.trim(), buildingName: buildingName.trim(), chicksPlaced, productionType });
  };

  return (
    <form className="card schedule-card batch-step-card" onSubmit={submit}>
      <h2 className="batch-step-title">{title}</h2>
      <p className="schedule-note">Ces informations identifient la bande. Le protocole se configure à l'étape suivante.</p>

      <div className="detail-grid">
        <label className="field">
          <span>Nom de la bande</span>
          <input value={batchName} onChange={(e) => setBatchName(e.target.value)} placeholder="ex. Bande printemps 2026" required />
        </label>
        <label className="field">
          <span>Poussins mis en place</span>
          <input type="number" min="1" value={chicksPlaced} onChange={(e) => setChicksPlaced(e.target.value)} placeholder="500" required />
        </label>
        <label className="field">
          <span>Nom du bâtiment</span>
          <input value={buildingName} onChange={(e) => setBuildingName(e.target.value)} placeholder="ex. Bâtiment A" required />
        </label>
        <label className="field">
          <span>Type de protocole</span>
          <select value={productionType} onChange={(e) => setProductionType(e.target.value)}>
            {PRODUCTION_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="batch-step-actions">
        <button type="submit" className="add-button batch-step-next" disabled={!complete}>Suivant</button>
      </div>
    </form>
  );
}
