import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import HouseProtocolForm from "../../components/HouseProtocolForm";
import BatchHeaderStep from "../../components/onboarding/BatchHeaderStep";
import BatchMethodChoice from "../../components/onboarding/BatchMethodChoice";
import BatchExcelImportScreen from "../../components/onboarding/BatchExcelImportScreen";
import { onboardingApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import { useOnboarding } from "../../context/OnboardingContext";
import { todayISO } from "../../utils/localDate";
import { buildProtocolSchedules } from "../../utils/protocolRows";
import useStockItemOptions from "../../hooks/useStockItemOptions";

function buildOnboardingRequest(payload, productionType) {
  return {
    house: {
      name: payload.house.buildingName,
      maxCapacity: payload.house.chicksPlaced,
    },
    batch: {
      name: payload.batchName,
      // Picked in the header step since 2026-09-11 (BatchHeaderStep) — this used to be
      // hardcoded "BROILER" because no screen ever asked.
      productionType: productionType || "BROILER",
      initialCount: payload.house.chicksPlaced,
      startDate: todayISO(),
      growthCycleValue: payload.house.growthCycle,
      growthCycleUnit: payload.house.growthCycleUnit.toUpperCase(),
      weighingFrequency: payload.weighingFrequency,
    },
    // Only the categories beyond the 5 auto-seeded defaults need to be sent —
    // apps.houses.signals seeds those from apps.protocols.models.DEFAULT_PROTOCOL_CATEGORIES.
    customCategories: payload.categories.slice(5).map(({ label, icon }) => ({ label, icon })),
    protocolLines: payload.protocolLines,
  };
}

/**
 * Batch creation, as a four-step sequence (2026-09-11):
 *
 *   header → choice → manual | excel
 *
 * The header step asks the handful of fields that identify the batch, then the user picks how
 * to fill the protocol. "Configurer manuellement" opens `HouseProtocolForm` exactly as this
 * page always did — same props, same save path, no behavior change. The Excel branch imports
 * the file and then hands off into that same form, pre-filled, so the user reviews what was
 * imported and saves through the identical code path rather than a parallel one.
 *
 * Reached by both entry points: first-time onboarding, and "+ Nouvelle bande" on a farm that
 * is already configured (`isAddingHouse` below).
 */
export default function OnboardingProtocolPage() {
  const { houseHeader, setHouseHeader, categories, setCategories, schedules, setSchedules } = useOnboarding();
  const [saving, setSaving] = useState(false);
  // Multi-batch first-time onboarding (2026-08-27) — houses already created via "Ajouter ce
  // bâtiment et en configurer un autre" this session, shown as a running list so the user has
  // feedback on what's already saved; `formKey` forces HouseProtocolForm to remount (fresh
  // internal state) after each addition, since changing its initial* props alone wouldn't
  // reset its own useState-held form data.
  const [addedHouses, setAddedHouses] = useState([]);
  const [formKey, setFormKey] = useState(0);
  // Lifted here rather than left in the header step, so stepping back and forth through the
  // sequence never loses what was typed.
  const [pendingHeader, setPendingHeader] = useState(houseHeader || {});
  const navigate = useNavigate();
  const location = useLocation();
  // Each step is its own history entry (router state), so the phone's back button steps back
  // through header -> choice -> manual/excel instead of leaving the page: it used to land on
  // /dashboard from any step, silently discarding the header and every protocol line typed
  // (campaign 9, finding B15). A reload onto a later step with no header falls back to the
  // header, since what was typed lives in this page's state, not in the URL.
  const historyStep = location.state?.batchStep || "header";
  const step = historyStep !== "header" && !pendingHeader.batchName ? "header" : historyStep;
  const setStep = (next) => navigate(location.pathname + location.search, { state: { ...location.state, batchStep: next } });
  const stepBack = () => navigate(-1);
  const { user, refreshMe } = useAuth();
  // The farm's existing articles, so the Consommation selector finds "Provende" after a reload
  // instead of offering to create it a second time.
  // Keyed on the step: articles the Excel path creates must be listed when the form opens.
  const stockItems = useStockItemOptions(user?.farm, step);
  // Farm already configured (stock/employees already exist) -> this is the
  // "+ Nouvelle bande" flow, not first-time onboarding. Skip straight to the
  // dashboard instead of forcing the stock/employees steps again, which
  // would otherwise let the stock step's full-replace PUT wipe out the
  // farm's existing stock items. Also: exactly one house/batch per invocation
  // (matches the button's own singular name) — no multi-batch loop here.
  const isAddingHouse = user?.is_configured;

  const handleSave = async (payload) => {
    setSaving(true);
    try {
      setHouseHeader({ ...payload.house, batchName: payload.batchName, weighingFrequency: payload.weighingFrequency });
      setCategories(payload.categories);
      // Kept as *form rows* (fromUnit, toUnit, ...), the shape HouseProtocolForm reopens with when
      // the user steps back to this page. It used to keep the API lines (from_unit, ...): back on
      // this step, "Suivant" threw in buildPayload and the page said the server was unreachable,
      // so a first-time user who went back to fix something could never save (campaign 9, B18).
      setSchedules(buildProtocolSchedules(
        payload.categories,
        payload.protocolLines.map((line) => ({ ...line, category: payload.categories[line.categoryIndex]?.id })),
      ));

      await onboardingApi.submit(buildOnboardingRequest(payload, pendingHeader.productionType));
      if (isAddingHouse) {
        await refreshMe();
        navigate("/dashboard", { replace: true });
      } else {
        navigate("/onboarding/stock");
      }
    } finally {
      setSaving(false);
    }
  };

  const handleAddAnother = async (payload) => {
    setSaving(true);
    try {
      const { data } = await onboardingApi.submit(buildOnboardingRequest(payload, pendingHeader.productionType));
      setAddedHouses((prev) => [...prev, { name: data.house.name }]);
      // Reset to the same empty state the page starts with on first load — the 5 default
      // categories, no lines — so the next house starts from scratch, not from what was just
      // submitted. `formKey` bump remounts HouseProtocolForm so this actually takes effect
      // (its category/schedule state lives in its own useState, initialized once from props).
      setHouseHeader({});
      setCategories(null);
      setSchedules({});
      setPendingHeader({});
      setFormKey((k) => k + 1);
      // Next batch starts at the top of the sequence again, same as the first one did.
      setStep("header");
    } finally {
      setSaving(false);
    }
  };

  // Excel branch: the imported rows become the form's initial data, then the user finishes in
  // the manual form — same save path, and a chance to review the file's content before it is
  // committed.
  const handleProtocolImported = (importedCategories, importedSchedules) => {
    setCategories(importedCategories);
    setSchedules(importedSchedules);
    setFormKey((k) => k + 1);
  };

  // Stays visible through the whole sequence, not just on the form: after "Ajouter ce bâtiment
  // et en configurer un autre" the next batch restarts at the header step, and the running list
  // (and the way out of the loop) has to still be reachable from there.
  const addedHousesPanel = addedHouses.length > 0 && (
    <div className="card schedule-card" style={{ marginBottom: 18 }}>
      <p className="schedule-note" style={{ marginBottom: 8 }}>
        {addedHouses.length} bâtiment{addedHouses.length > 1 ? "s" : ""} déjà configuré
        {addedHouses.length > 1 ? "s" : ""} :
      </p>
      <ul style={{ margin: "0 0 12px", paddingLeft: 18, fontSize: 13.5, color: "#374548" }}>
        {addedHouses.map((h, i) => <li key={i}>{h.name || "Bâtiment sans nom"}</li>)}
      </ul>
      <button className="add-button" style={{ marginTop: 0 }} onClick={() => navigate("/onboarding/stock")}>
        Continuer sans ajouter d'autre bâtiment
      </button>
    </div>
  );

  if (step === "header") {
    return (
      <>
        {addedHousesPanel}
        <BatchHeaderStep
          initial={pendingHeader}
          onNext={(header) => {
            setPendingHeader(header);
            setStep("choice");
          }}
        />
      </>
    );
  }

  if (step === "choice") {
    return (
      <>
        {addedHousesPanel}
        <BatchMethodChoice
          onSelectManual={() => setStep("manual")}
          onSelectExcel={() => setStep("excel")}
          onBack={stepBack}
        />
      </>
    );
  }

  if (step === "excel") {
    return (
      <>
        {addedHousesPanel}
        <BatchExcelImportScreen
          farmId={user.farm}
          onProtocolImported={handleProtocolImported}
          onContinue={() => setStep("manual")}
          onBack={stepBack}
        />
      </>
    );
  }

  return (
    <>
      {addedHousesPanel}
      <div className="batch-step-actions" style={{ marginTop: 0, marginBottom: 14 }}>
        <button type="button" className="batch-back-button" onClick={stepBack}>
          Retour
        </button>
      </div>
      <HouseProtocolForm
        key={formKey}
        initialHeader={{ ...houseHeader, ...pendingHeader }}
        initialCategories={categories}
        initialSchedules={schedules}
        mode="onboarding"
        saving={saving}
        farmId={user.farm}
        stockItems={stockItems}
        onSave={handleSave}
        onAddAnother={isAddingHouse ? undefined : handleAddAnother}
        submitLabel={isAddingHouse ? "Créer la bande" : undefined}
      />
    </>
  );
}
