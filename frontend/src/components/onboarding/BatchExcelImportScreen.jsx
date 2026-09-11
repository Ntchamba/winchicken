import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import ExcelImportCard from "./ExcelImportCard";
import { protocolImportApi, stockApi } from "../../api/endpoints";
import { getServerErrorMessage } from "../../api/errors";
import { DEFAULT_CATEGORIES } from "../../utils/protocolRows";
import { resolveProtocolImportRows } from "../../utils/protocolImportResolve";
import "../../pages/onboarding/batch-flow.css";

/**
 * The "Importer via Excel" branch of batch creation: one card per type of data.
 *
 * Each import reuses the system that already exists for it, unchanged — the protocol file is
 * parsed by `protocolImportApi.parse` and resolved by the same helper `HouseProtocolForm`
 * uses, and the stock file goes to `stockApi.importXlsx`, the update-or-create importer
 * behind "Mettre à jour le stock" (it never deletes an absent article and never touches
 * quantities, so running it here is safe even on a farm that already has stock). Finances has
 * no import endpoint at all yet, so its card is present but inert.
 *
 * Categories are kept locally and handed back with the schedules, because during batch
 * creation the house does not exist yet — a category named only by the file has no database
 * id to get until the whole onboarding payload is submitted. The first five entries stay the
 * backend's default categories in order, which is the contract
 * `OnboardingProtocolPage.buildOnboardingRequest` relies on (`categories.slice(5)`).
 *
 * @param {?number} farmId
 * @param {(categories: object[], schedules: object) => void} onProtocolImported
 * @param {() => void} onContinue - Enabled once a protocol file has been imported.
 * @param {() => void} onBack
 */
export default function BatchExcelImportScreen({ farmId, onProtocolImported, onContinue, onBack }) {
  const [categories, setCategories] = useState(DEFAULT_CATEGORIES);
  const [stockItemList, setStockItemList] = useState([]);

  const [protocolBusy, setProtocolBusy] = useState(false);
  const [protocolResult, setProtocolResult] = useState(null);
  const [protocolError, setProtocolError] = useState("");
  const [protocolDone, setProtocolDone] = useState(false);

  const [stockBusy, setStockBusy] = useState(false);
  const [stockResult, setStockResult] = useState(null);
  const [stockError, setStockError] = useState("");

  useEffect(() => {
    if (!farmId) return;
    stockApi.items(farmId).then(({ data }) => {
      setStockItemList((data.items || []).map((i) => ({ item_code: i.item_code, name: i.name, unit: i.unit })));
    }).catch(() => {});
  }, [farmId]);

  const importProtocol = async (file) => {
    setProtocolBusy(true);
    setProtocolError("");
    setProtocolResult(null);

    // The categories a file names are collected here rather than read back from state: the
    // parent needs the complete list (defaults + everything this file added) in one piece,
    // and a setState during the resolve wouldn't be visible to it in time.
    const nextCategories = [...categories];
    const nextStockItems = [...stockItemList];

    // Onboarding semantics, identical to HouseProtocolForm's: the house doesn't exist, so a
    // new category is a local entry with a temporary key, resolved server-side by position.
    const createCategory = async (label, icon = "Package") => {
      const local = { id: `pending-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`, label, icon };
      nextCategories.push(local);
      return local;
    };

    const createStockItem = async (name, categoryLabel, unit) => {
      const { data } = await stockApi.addItem(farmId, { name, unit: unit || "kg", category_hint: categoryLabel });
      nextStockItems.push(data);
      return data;
    };

    try {
      const { data } = await protocolImportApi.parse(file);
      const { schedules } = await resolveProtocolImportRows(data, {
        categories, stockItemList, farmId, createCategory, createStockItem,
      });

      setCategories(nextCategories);
      setStockItemList(nextStockItems);

      if (schedules === null) {
        setProtocolResult({ imported: 0, skipped: data.skipped || [], warnings: data.warnings || [] });
        return;
      }

      setProtocolResult({ imported: data.imported, skipped: data.skipped || [], warnings: data.warnings || [] });
      setProtocolDone(true);
      onProtocolImported(nextCategories, schedules);
    } catch (err) {
      setProtocolError(
        err?.isAxiosError
          ? getServerErrorMessage(err, "Échec de l'import du fichier Excel.")
          : err?.message || "Échec de l'import du fichier Excel.",
      );
    } finally {
      setProtocolBusy(false);
    }
  };

  const importStock = async (file) => {
    setStockBusy(true);
    setStockError("");
    setStockResult(null);
    try {
      const { data } = await stockApi.importXlsx(farmId, file);
      setStockResult(data);
    } catch (err) {
      setStockError(getServerErrorMessage(err, "Échec de l'import du fichier Excel."));
    } finally {
      setStockBusy(false);
    }
  };

  return (
    <div className="card schedule-card batch-step-card">
      <h2 className="batch-step-title">Importer via Excel</h2>
      <p className="schedule-note">
        Importez au moins le protocole pour continuer. Vous pourrez tout relire et ajuster
        avant d'enregistrer la bande.
      </p>

      <div className="batch-card-grid">
        <ExcelImportCard
          title="Protocole"
          hint="Aliments, soins et créneaux horaires, par tranche de jours."
          templateUrl={protocolImportApi?.templateUrl}
          onImport={importProtocol}
          importing={protocolBusy}
          errorMessage={protocolError || null}
        >
          {protocolResult && (
            <p
              role="status"
              className={`batch-import-summary ${
                protocolResult.skipped.length || protocolResult.warnings.length
                  ? "batch-import-summary--warn"
                  : "batch-import-summary--ok"
              }`}
            >
              <strong>
                {protocolResult.imported} ligne{protocolResult.imported > 1 ? "s" : ""} importée
                {protocolResult.imported > 1 ? "s" : ""}
                {protocolResult.skipped.length > 0 &&
                  `, ${protocolResult.skipped.length} ignorée${protocolResult.skipped.length > 1 ? "s" : ""}`}
                .
              </strong>
              {(protocolResult.skipped.length > 0 || protocolResult.warnings.length > 0) && (
                <span style={{ display: "block", marginTop: 4 }}>
                  {protocolResult.skipped.map((s) => `Ligne ${s.line} : ${s.reason}`).join(" · ")}
                  {protocolResult.warnings.join(" · ")}
                </span>
              )}
            </p>
          )}
        </ExcelImportCard>

        <ExcelImportCard
          title="Stock"
          hint="Articles, catégories, seuils et fournisseurs."
          templateUrl={stockApi?.importTemplateUrl}
          onImport={importStock}
          importing={stockBusy}
          errorMessage={stockError || null}
        >
          {stockResult && (
            <p
              role="status"
              className={`batch-import-summary ${
                stockResult.skipped.length ? "batch-import-summary--warn" : "batch-import-summary--ok"
              }`}
            >
              <strong>
                {stockResult.updated} mise{stockResult.updated > 1 ? "s" : ""} à jour,{" "}
                {stockResult.created} créée{stockResult.created > 1 ? "s" : ""},{" "}
                {stockResult.skipped.length} ignorée{stockResult.skipped.length > 1 ? "s" : ""}.
              </strong>
            </p>
          )}
        </ExcelImportCard>

        <ExcelImportCard
          title="Finances"
          hint="Recettes et dépenses — l'import n'est pas encore disponible."
          badge="Bientôt disponible"
          disabled
        />
      </div>

      <div className="batch-step-actions">
        <button type="button" className="batch-back-button" onClick={onBack}>
          <ArrowLeft size={15} strokeWidth={2.2} /> Retour
        </button>
        <button type="button" className="add-button batch-step-next" onClick={onContinue} disabled={!protocolDone}>
          Continuer
        </button>
      </div>
    </div>
  );
}
