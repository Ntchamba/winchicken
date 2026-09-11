import { ArrowLeft, FileSpreadsheet, PencilLine } from "lucide-react";
import "../../pages/onboarding/batch-flow.css";

/**
 * Step between the batch header and the protocol itself: fill the protocol by hand, or from
 * an Excel file. "Configurer manuellement" opens the unchanged `HouseProtocolForm`.
 *
 * @param {() => void} onSelectManual
 * @param {() => void} onSelectExcel
 * @param {() => void} onBack - Returns to the header step, keeping what was typed there.
 */
export default function BatchMethodChoice({ onSelectManual, onSelectExcel, onBack }) {
  return (
    <div className="card schedule-card batch-step-card">
      <h2 className="batch-step-title">Comment voulez-vous configurer cette bande ?</h2>
      <p className="schedule-note">
        Les deux méthodes aboutissent au même protocole — l'import Excel vous fait simplement
        gagner la saisie ligne par ligne.
      </p>

      <div className="batch-card-grid">
        <button type="button" className="batch-choice-card" onClick={onSelectManual}>
          <span className="batch-choice-icon"><PencilLine size={22} strokeWidth={1.9} /></span>
          <span className="batch-choice-name">Configurer manuellement</span>
          <p className="batch-choice-hint">
            Saisissez le protocole, les créneaux et les ressources directement dans le formulaire.
          </p>
        </button>

        <button type="button" className="batch-choice-card" onClick={onSelectExcel}>
          <span className="batch-choice-icon"><FileSpreadsheet size={22} strokeWidth={1.9} /></span>
          <span className="batch-choice-name">Importer via Excel</span>
          <p className="batch-choice-hint">
            Partez d'un fichier .xlsx — un modèle est téléchargeable pour chaque type de données.
          </p>
        </button>
      </div>

      <div className="batch-step-actions">
        <button type="button" className="batch-back-button" onClick={onBack}>
          <ArrowLeft size={15} strokeWidth={2.2} /> Retour
        </button>
      </div>
    </div>
  );
}
