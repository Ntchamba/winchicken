import React from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import HouseProtocolForm from "../HouseProtocolForm";
import { housesApi, protocolImportApi, stockApi } from "../../api/endpoints";

vi.mock("../../api/endpoints", () => ({
  protocolImportApi: { parse: vi.fn(), templateUrl: "http://test/protocols/import-template.xlsx" },
  stockApi: { addItem: vi.fn() },
  housesApi: { addProtocolCategory: vi.fn() },
}));

// Regression (2026-09-01): callers that don't pass `stockItems` (OnboardingProtocolPage,
// HouseProtocolPage) fell on a `stockItems = []` default — a fresh array identity every
// render — which made `useEffect(() => setStockItemList(stockItems), [stockItems])` re-fire
// on every render and spin into "Maximum update depth exceeded", freezing the page so the
// "Suivant" button and route changes never committed. The default is now a stable module
// constant. This pins that the no-prop render is loop-free.
describe("HouseProtocolForm — no infinite render loop without a stockItems prop", () => {
  afterEach(() => vi.restoreAllMocks());

  test("renders without stockItems and never hits max update depth", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(<HouseProtocolForm mode="onboarding" onSave={() => {}} />);
    expect(screen.getByRole("button", { name: "Suivant" })).toBeInTheDocument();
    const loopErrors = errorSpy.mock.calls
      .flat()
      .filter((a) => typeof a === "string" && a.includes("Maximum update depth"));
    expect(loopErrors).toEqual([]);
  });
});

// Part B (docs/deviations.md Part 15): the onboarding wizard's own "Suivant" button
// (HouseProtocolForm's save-bar button, labeled "Suivant" in mode="onboarding") must stay
// disabled until the protocol actually has at least one line — `disabled={saving ||
// totalRows === 0}`. This exercises the real button through a real user interaction
// ("Charger un modèle" seeds the starter template), not a synthetic prop.
describe("HouseProtocolForm — Suivant enables only once data is entered", () => {
  test("disabled with an empty protocol, enabled after a template AND a batch name", async () => {
    render(<HouseProtocolForm mode="onboarding" onSave={() => {}} />);

    const nextButton = screen.getByRole("button", { name: "Suivant" });
    expect(nextButton).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: /charger le modèle de départ/i }));
    // Part A: protocol rows alone are not enough — the batch name is now required.
    expect(nextButton).toBeDisabled();
    expect(screen.getByText("Le nom de la bande est requis.")).toBeInTheDocument();

    await userEvent.type(screen.getByRole("textbox", { name: /nom de la bande/i }), "Bande printemps");
    expect(nextButton).toBeEnabled();
  });

  test("a whitespace-only batch name does not enable Suivant", async () => {
    render(<HouseProtocolForm mode="onboarding" onSave={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: /charger le modèle de départ/i }));
    await userEvent.type(screen.getByRole("textbox", { name: /nom de la bande/i }), "   ");
    expect(screen.getByRole("button", { name: "Suivant" })).toBeDisabled();
  });
});

// Part B, "Modifier" modal requirements (docs/deviations.md Part 15): checked what this
// codebase actually has before writing assertions — there is no "Réinitialiser" button
// anywhere in this component or ProtocolEditModal (grepped both files; the only two
// "Annuler" buttons found are for canceling the add-category flow and the delete-category
// confirmation, unrelated sub-flows, not a form-level cancel/reset). What *is* real and
// regression-worthy: management mode must show the management save label and must never
// render the onboarding-only "Suivant" wizard button, and must load with the data it was
// given rather than blank fields.
describe("HouseProtocolForm — management mode (used by the \"Modifier\" modal)", () => {
  const initialHeader = {
    buildingName: "Bâtiment A", chicksPlaced: 500, growthCycle: 42, growthCycleUnit: "Day",
    batchName: "Bande Existante", weighingFrequency: "WEEK",
  };
  const initialCategories = [{ id: 1, label: "Alimentation", icon: "Soup" }];
  const initialSchedules = { 1: [{ id: 10, fromValue: 1, fromUnit: "Day", toValue: 15, toUnit: "Day", what: "Aliment démarrage", details: "" }] };

  test("shows the management save label, not the onboarding stepper button", () => {
    render(
      <HouseProtocolForm
        mode="management"
        houseCode="H-1"
        initialHeader={initialHeader}
        initialCategories={initialCategories}
        initialSchedules={initialSchedules}
        onSave={() => {}}
      />
    );

    expect(screen.getByRole("button", { name: "Enregistrer le protocole" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Suivant" })).not.toBeInTheDocument();
  });

  test("batchEditable=false hides the batch name, disables the other batch fields, shows a notice", () => {
    render(
      <HouseProtocolForm
        mode="management"
        houseCode="H-1"
        batchEditable={false}
        initialHeader={{ ...initialHeader, batchName: "" }}
        initialCategories={initialCategories}
        initialSchedules={initialSchedules}
        onSave={() => {}}
      />
    );

    expect(screen.getByText(/ce bâtiment n'a pas de bande active/i)).toBeInTheDocument();
    // 2026-09-11: the batch name is now hidden outright rather than shown disabled — there is
    // no batch to name, and an inert field only invites "why can't I type here?".
    expect(screen.queryByRole("textbox", { name: /nom de la bande/i })).not.toBeInTheDocument();
    // The remaining batch-scoped fields stay visible but disabled: they describe the protocol
    // the next batch will inherit, so their values are still worth seeing.
    expect(screen.getByRole("spinbutton", { name: /poussins mis en place/i })).toBeDisabled();
    expect(screen.getByRole("combobox", { name: /fréquence de pesée/i })).toBeDisabled();
    // the house name stays editable — that IS persistable without a batch
    expect(screen.getByRole("textbox", { name: /nom du bâtiment/i })).toBeEnabled();
  });

  test("batchEditable=false still shows the batch name once a batch exists", () => {
    render(
      <HouseProtocolForm
        mode="management"
        houseCode="H-1"
        batchEditable
        initialHeader={{ ...initialHeader, batchName: "Bande printemps" }}
        initialCategories={initialCategories}
        initialSchedules={initialSchedules}
        onSave={() => {}}
      />
    );

    const field = screen.getByRole("textbox", { name: /nom de la bande/i });
    expect(field).toBeInTheDocument();
    expect(field).toBeEnabled();
    expect(field).toHaveValue("Bande printemps");
  });

  test("batchEditable defaults to true — no notice, band name editable", () => {
    render(
      <HouseProtocolForm
        mode="management"
        houseCode="H-1"
        initialHeader={initialHeader}
        initialCategories={initialCategories}
        initialSchedules={initialSchedules}
        onSave={() => {}}
      />
    );
    expect(screen.queryByText(/ce bâtiment n'a pas de bande active/i)).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /nom de la bande/i })).toBeEnabled();
  });

  test("loads with the existing protocol data, not empty fields", () => {
    render(
      <HouseProtocolForm
        mode="management"
        houseCode="H-1"
        initialHeader={initialHeader}
        initialCategories={initialCategories}
        initialSchedules={initialSchedules}
        onSave={() => {}}
      />
    );

    expect(screen.getByDisplayValue("Bâtiment A")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Bande Existante")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Aliment démarrage")).toBeInTheDocument();
    // Empty-protocol state would disable Suivant/Enregistrer (totalRows === 0) — asserting it's
    // enabled is an indirect but real check that the seeded row actually landed in state.
    expect(screen.getByRole("button", { name: "Enregistrer le protocole" })).toBeEnabled();
  });
});

// Excel import (docs/excel-import.md): a destructive **full replacement** — the file's rows
// become the whole protocol (not appended), behind an explicit warning; missing categories /
// stock items are auto-created; a clear summary lists every skipped row.
describe("HouseProtocolForm — import Excel (full replacement)", () => {
  afterEach(() => vi.clearAllMocks());

  const twoRows = {
    data: {
      rows: [
        { category: "Alimentation", fromValue: 1, toValue: 15, untilEnd: false,
          what: "Aliment démarrage", details: "3000 kcal", consumption: "Provende", quantityPerDay: 40 },
        { category: "Biosécurité", fromValue: 1, toValue: null, untilEnd: true,
          what: "Pédiluve désinfectant", details: "", consumption: null, quantityPerDay: null },
      ],
      imported: 2,
      skipped: [{ line: 4, reason: "action manquante" }],
    },
  };

  test("warns before parsing anything, and does nothing on cancel", async () => {
    render(<HouseProtocolForm mode="onboarding" farmId={7} onSave={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: /Importer un fichier Excel/i }));

    expect(screen.getByText(/remplacer toutes les lignes de protocole actuelles/i)).toBeInTheDocument();
    expect(screen.getByText(/irréversible/i)).toBeInTheDocument();
    expect(protocolImportApi.parse).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Annuler" }));
    expect(screen.queryByText(/remplacer toutes les lignes/i)).not.toBeInTheDocument();
  });

  test("replaces every existing row with the file's rows, auto-creates category + stock item, reports skips", async () => {
    protocolImportApi.parse.mockResolvedValue(twoRows);
    stockApi.addItem.mockResolvedValue({ data: { item_code: "FEE-7-001", name: "Provende", unit: "kg" } });
    housesApi.addProtocolCategory.mockResolvedValue({ data: { id: 2, label: "Biosécurité", icon: "Package" } });

    const { container } = render(
      <HouseProtocolForm
        mode="management"
        houseCode="H-1"
        farmId={7}
        initialCategories={[{ id: 1, label: "Alimentation", icon: "Soup" }]}
        initialSchedules={{ 1: [{ id: 99, fromValue: 1, fromUnit: "Day", toValue: 5, toUnit: "Day", what: "Vieille ligne à supprimer", details: "" }] }}
        onSave={() => {}}
      />
    );

    expect(screen.getByDisplayValue("Vieille ligne à supprimer")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Importer un fichier Excel/i }));
    await userEvent.click(screen.getByRole("button", { name: /Choisir le fichier et remplacer/i }));
    await userEvent.upload(container.querySelector('input[type="file"]'), new File(["xlsx"], "protocole.xlsx"));

    // pre-existing row is gone, the file's row is in
    expect(await screen.findByDisplayValue("Aliment démarrage")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("Vieille ligne à supprimer")).not.toBeInTheDocument();

    expect(screen.getByText(/Protocole remplacé — 2 lignes importées avec succès, 1 ligne ignorée/i)).toBeInTheDocument();
    expect(screen.getByText("Ligne 4 : action manquante")).toBeInTheDocument();
    expect(stockApi.addItem).toHaveBeenCalledWith(7, expect.objectContaining({ name: "Provende", category_hint: "Alimentation" }));
    expect(screen.getByText("Biosécurité")).toBeInTheDocument(); // a new category tab
  });

  test("a file with no usable row does NOT wipe the protocol (guard against accidental erase)", async () => {
    protocolImportApi.parse.mockResolvedValue({ data: { rows: [], imported: 0, skipped: [{ line: 2, reason: "action manquante" }] } });
    const { container } = render(
      <HouseProtocolForm
        mode="management" houseCode="H-1" farmId={7}
        initialCategories={[{ id: 1, label: "Alimentation", icon: "Soup" }]}
        initialSchedules={{ 1: [{ id: 99, fromValue: 1, fromUnit: "Day", toValue: 5, toUnit: "Day", what: "Ligne conservée", details: "" }] }}
        onSave={() => {}}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: /Importer un fichier Excel/i }));
    await userEvent.click(screen.getByRole("button", { name: /Choisir le fichier et remplacer/i }));
    await userEvent.upload(container.querySelector('input[type="file"]'), new File(["x"], "empty.xlsx"));

    expect(await screen.findByText("Ligne 2 : action manquante")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Ligne conservée")).toBeInTheDocument(); // untouched
  });

  test("a parse failure shows the server message, no rows added", async () => {
    protocolImportApi.parse.mockRejectedValue({
      isAxiosError: true,
      response: { data: { detail: "En-têtes de colonnes introuvables : « Action »." } },
    });
    const { container } = render(<HouseProtocolForm mode="onboarding" farmId={7} onSave={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: /Importer un fichier Excel/i }));
    await userEvent.click(screen.getByRole("button", { name: /Choisir le fichier et remplacer/i }));
    await userEvent.upload(container.querySelector('input[type="file"]'), new File(["x"], "bad.xlsx"));
    expect(await screen.findByText(/En-têtes de colonnes introuvables/)).toBeInTheDocument();
  });

  test("imports time slots, a new resource with its file unit, and lists a malformed-créneau warning", async () => {
    protocolImportApi.parse.mockResolvedValue({
      data: {
        rows: [{
          category: "Alimentation", fromValue: 1, toValue: 15, untilEnd: false,
          what: "Nourrissage", details: "", consumption: "Provende", unit: "sac", quantityPerDay: 40,
          timeSlots: [{ startTime: "06:30", endTime: "07:30" }, { startTime: "18:30", endTime: "19:30" }],
        }],
        imported: 1,
        skipped: [],
        warnings: [{ line: 3, reason: "créneau mal formé « 06h30-07h30 » ignoré, ligne importée sans cet horaire" }],
      },
    });
    stockApi.addItem.mockResolvedValue({ data: { item_code: "FEE-7-001", name: "Provende", unit: "sac" } });

    const { container } = render(<HouseProtocolForm mode="onboarding" farmId={7} onSave={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: /Importer un fichier Excel/i }));
    await userEvent.click(screen.getByRole("button", { name: /Choisir le fichier et remplacer/i }));
    await userEvent.upload(container.querySelector('input[type="file"]'), new File(["x"], "p.xlsx"));

    // the two time windows are rendered as removable chips on the imported row
    expect(await screen.findByDisplayValue("Nourrissage")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /Supprimer le créneau/ })).toHaveLength(2);

    // the new resource was created with the file's unit, not the hardcoded "kg"
    expect(stockApi.addItem).toHaveBeenCalledWith(7, expect.objectContaining({ name: "Provende", unit: "sac" }));

    // the malformed-créneau warning is listed even though the row imported
    expect(screen.getByText(/Ligne 3 : créneau mal formé/)).toBeInTheDocument();
  });
});

// Campaign 3 (browser): "Ajouter un créneau" → both times → ✓ threw
// "ReferenceError: nextId is not defined" (the counter had moved to utils/protocolRows), so no
// time slot could be added from the form at all; the stale "Les deux heures sont requises."
// was the only thing on screen.
describe("HouseProtocolForm — adding a time slot", () => {
  test("a slot typed into the two time fields is added as a chip and saved with the line", async () => {
    const onSave = vi.fn();
    const { container } = render(<HouseProtocolForm mode="onboarding" onSave={onSave} />);
    await userEvent.type(screen.getByRole("textbox", { name: /nom de la bande/i }), "Bande test");
    await userEvent.click(screen.getByRole("button", { name: /ajouter une ligne/i }));
    await userEvent.type(screen.getByPlaceholderText(/aliment démarrage/i), "Aliment");
    await userEvent.click(screen.getByRole("button", { name: /ajouter un créneau/i }));

    const [start, end] = container.querySelectorAll('input[type="time"]');
    await userEvent.type(start, "07:00");
    await userEvent.type(end, "08:00");
    await userEvent.click(screen.getByRole("button", { name: "Confirmer le créneau" }));

    expect(screen.queryByText("Les deux heures sont requises.")).not.toBeInTheDocument();
    expect(container.querySelectorAll('input[type="time"]')).toHaveLength(0);
    expect(screen.getByText("07:00–08:00")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
    const line = onSave.mock.calls[0][0].protocolLines[0];
    expect(line.time_slots).toEqual([{ start_time: "07:00", end_time: "08:00" }]);
  });
});
