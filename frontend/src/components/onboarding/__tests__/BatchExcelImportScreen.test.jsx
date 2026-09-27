import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import BatchExcelImportScreen from "../BatchExcelImportScreen";
import { protocolImportApi, stockApi } from "../../../api/endpoints";

vi.mock("../../../api/endpoints", () => ({
  protocolImportApi: { parse: vi.fn(), templateUrl: "http://test/protocols/import-template.xlsx" },
  stockApi: {
    items: vi.fn(),
    addItem: vi.fn(),
    importXlsx: vi.fn(),
    importTemplateUrl: "http://test/stock-items/import-template.xlsx",
  },
}));

const xlsx = (name) => new File(["x"], name, { type: "application/vnd.ms-excel" });

const cardFor = (title) => screen.getByText(title).closest(".batch-import-card");
const uploadTo = (title, file) =>
  userEvent.upload(cardFor(title).querySelector('input[type="file"]'), file);
const confirmImport = () => userEvent.click(screen.getByRole("button", { name: /Confirmer l'import/i }));

// The server's column-mapping report (apps/core/column_matching.py). Shaped exactly like the
// real payload so the preview is exercised, not stubbed around.
const columnsReport = (overrides = {}) => ({
  matches: [
    { key: "category", label: "Catégorie", header: "Rubrique", index: 0, method: "exact", confidence: 1, note: "", required: true },
    { key: "from_value", label: "De", header: "Jour début", index: 1, method: "exact", confidence: 1, note: "", required: true },
    { key: "what", label: "Action", header: "Tache", index: 2, method: "fuzzy", confidence: 0.889, note: "Correspondance approximative — vérifiez que la colonne est la bonne.", required: true },
    { key: "unit", label: "Unité", header: "", index: null, method: "default", confidence: 0, note: "Sans colonne d'unité, une ressource créée par l'import prend « kg ».", required: false },
  ],
  unknownHeaders: [],
  unresolved: [],
  ...overrides,
});

const parsed = (rows, extra = {}) => ({
  data: { imported: rows.length, skipped: [], warnings: [], columns: columnsReport(), rows, ...extra },
});

function renderScreen(props = {}) {
  return render(
    <BatchExcelImportScreen
      farmId={1}
      onProtocolImported={props.onProtocolImported || vi.fn()}
      onContinue={props.onContinue || vi.fn()}
      onBack={props.onBack || vi.fn()}
    />,
  );
}

describe("BatchExcelImportScreen", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    stockApi.items.mockResolvedValue({ data: { items: [] } });
  });

  test("imports a protocol file and hands the resolved rows up once confirmed", async () => {
    protocolImportApi.parse.mockResolvedValue(parsed([
      { category: "Alimentation", fromValue: 1, toValue: 10, untilEnd: false, what: "Démarrage", details: "", consumption: null, timeSlots: [{ startTime: "07:00", endTime: "09:00" }] },
      { category: "Biosécurité", fromValue: 1, toValue: 5, untilEnd: false, what: "Pédiluve", details: "", consumption: null, timeSlots: [] },
    ]));
    const onProtocolImported = vi.fn();
    renderScreen({ onProtocolImported });

    await uploadTo("Protocole", xlsx("protocole.xlsx"));

    // Nothing is handed up until the user has seen the mapping and confirmed it.
    expect(await screen.findByText(/Vérifiez les colonnes reconnues/i)).toBeInTheDocument();
    expect(onProtocolImported).not.toHaveBeenCalled();

    await confirmImport();

    await waitFor(() => expect(onProtocolImported).toHaveBeenCalledTimes(1));
    const [categories, schedules] = onProtocolImported.mock.calls[0];

    // The 5 backend defaults keep their positions; the file's own category is appended after
    // them — buildOnboardingRequest slices at 5 to find the custom ones.
    expect(categories.slice(0, 5).map((c) => c.label)).toEqual([
      "Alimentation", "Température", "Santé et soins", "Vaccination", "Nettoyage",
    ]);
    expect(categories[5]).toMatchObject({ label: "Biosécurité" });

    const allRows = Object.values(schedules).flat();
    expect(allRows).toHaveLength(2);
    expect(schedules["default-0"][0]).toMatchObject({ what: "Démarrage" });
    expect(schedules["default-0"][0].timeSlots[0]).toMatchObject({ startTime: "07:00", endTime: "09:00" });
    expect(schedules[categories[5].id][0]).toMatchObject({ what: "Pédiluve" });
  });

  test("the preview names the file's header for each column and how it was matched", async () => {
    protocolImportApi.parse.mockResolvedValue(parsed([
      { category: "Alimentation", fromValue: 1, toValue: 3, untilEnd: false, what: "Miettes", details: "", consumption: null, timeSlots: [] },
    ]));
    renderScreen();

    await uploadTo("Protocole", xlsx("protocole.xlsx"));

    const preview = (await screen.findByText(/Vérifiez les colonnes reconnues/i)).closest(".import-preview");
    // Synonym match: the file said "Rubrique", the app understood "Catégorie".
    expect(within(preview).getByText("Rubrique")).toBeInTheDocument();
    expect(within(preview).getByText("Catégorie")).toBeInTheDocument();
    // Fuzzy matches are called out with their confidence, so a close-but-wrong header is visible.
    expect(within(preview).getByText(/Approximative · 89 %/)).toBeInTheDocument();
    // An absent optional column reports the default it will fall back to.
    expect(within(preview).getByText(/Valeur par défaut/)).toBeInTheDocument();
    expect(within(preview).getByText(/prend « kg »/)).toBeInTheDocument();
  });

  test("an unresolved required column blocks confirmation and says which one", async () => {
    protocolImportApi.parse.mockResolvedValue({
      data: {
        imported: 0, skipped: [], warnings: [], rows: [],
        columns: columnsReport({
          unresolved: ["Catégorie"],
          matches: [
            { key: "category", label: "Catégorie", header: "", index: null, method: "missing", confidence: 0, note: "", required: true },
          ],
          unknownHeaders: ["Numéro de facture"],
        }),
      },
    });
    const onProtocolImported = vi.fn();
    renderScreen({ onProtocolImported });

    await uploadTo("Protocole", xlsx("mauvaises-colonnes.xlsx"));

    expect(await screen.findByText(/Colonne obligatoire introuvable/i)).toBeInTheDocument();
    expect(screen.getByText(/« Catégorie »/)).toBeInTheDocument();
    expect(screen.getByText(/Numéro de facture/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Confirmer l'import/i })).toBeDisabled();
    expect(onProtocolImported).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Continuer" })).toBeDisabled();
  });

  test("cancelling the preview imports nothing and returns to the cards", async () => {
    protocolImportApi.parse.mockResolvedValue(parsed([
      { category: "Alimentation", fromValue: 1, toValue: 3, untilEnd: false, what: "Miettes", details: "", consumption: null, timeSlots: [] },
    ]));
    const onProtocolImported = vi.fn();
    renderScreen({ onProtocolImported });

    await uploadTo("Protocole", xlsx("protocole.xlsx"));
    await screen.findByText(/Vérifiez les colonnes reconnues/i);
    await userEvent.click(screen.getByRole("button", { name: /Annuler/i }));

    expect(screen.queryByText(/Vérifiez les colonnes reconnues/i)).not.toBeInTheDocument();
    expect(onProtocolImported).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Continuer" })).toBeDisabled();
  });

  test("a protocol file with no usable row reports the skips and does not unlock 'Continuer'", async () => {
    protocolImportApi.parse.mockResolvedValue({
      data: {
        imported: 0, skipped: [{ line: 2, reason: "Catégorie inconnue" }], warnings: [], rows: [],
        columns: columnsReport(),
      },
    });
    const onProtocolImported = vi.fn();
    renderScreen({ onProtocolImported });

    await uploadTo("Protocole", xlsx("vide.xlsx"));

    expect(await screen.findByText(/Catégorie inconnue/)).toBeInTheDocument();
    expect(onProtocolImported).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Continuer" })).toBeDisabled();
  });

  test("surfaces the server's message when the protocol file is rejected", async () => {
    const err = new Error("bad");
    err.isAxiosError = true;
    err.response = { data: { detail: "Colonne « Catégorie » manquante." } };
    protocolImportApi.parse.mockRejectedValue(err);
    renderScreen();

    await uploadTo("Protocole", xlsx("mauvais.xlsx"));

    expect(await screen.findByText(/Colonne « Catégorie » manquante./)).toBeInTheDocument();
  });

  test("previews a stock file as a dry run, then commits it on confirmation", async () => {
    stockApi.importXlsx
      .mockResolvedValueOnce({ data: { updated: 3, created: 2, skipped: [], columns: columnsReport(), dryRun: true } })
      .mockResolvedValueOnce({ data: { updated: 3, created: 2, skipped: [], columns: columnsReport() } });
    renderScreen();

    const file = xlsx("stock.xlsx");
    await uploadTo("Stock", file);

    // First call is the dry run — the server rolls it back, so nothing is written yet.
    await waitFor(() => expect(stockApi.importXlsx).toHaveBeenCalledWith(1, file, { dryRun: true }));
    expect(await screen.findByText(/3 articles à mettre à jour, 2 à créer/i)).toBeInTheDocument();
    expect(stockApi.importXlsx).toHaveBeenCalledTimes(1);

    await confirmImport();

    // Second call has no dry-run flag: this is the one that commits.
    await waitFor(() => expect(stockApi.importXlsx).toHaveBeenCalledTimes(2));
    expect(stockApi.importXlsx.mock.calls[1]).toEqual([1, file]);
    expect(await screen.findByText(/3 mises à jour, 2 créées, 0 ignorée/i)).toBeInTheDocument();
  });

  test("cancelling a stock preview writes nothing", async () => {
    stockApi.importXlsx.mockResolvedValue({
      data: { updated: 1, created: 0, skipped: [], columns: columnsReport(), dryRun: true },
    });
    renderScreen();

    await uploadTo("Stock", xlsx("stock.xlsx"));
    await screen.findByText(/1 article à mettre à jour/i);
    await userEvent.click(screen.getByRole("button", { name: /Annuler/i }));

    expect(screen.queryByText(/Vérifiez les colonnes reconnues/i)).not.toBeInTheDocument();
    expect(stockApi.importXlsx).toHaveBeenCalledTimes(1); // only the dry run
  });

  // No finance import endpoint exists (apps/finance/urls.py has none) — there is no Finances
  // card at all, rather than a disabled one that only made the screen look broken.
  test("there is no Finances card", async () => {
    renderScreen();
    await waitFor(() => expect(stockApi.items).toHaveBeenCalled());
    expect(screen.queryByText("Finances")).not.toBeInTheDocument();
    expect(screen.queryByText("Bientôt disponible")).not.toBeInTheDocument();
  });

  test("'Continuer' only unlocks after a confirmed protocol import", async () => {
    protocolImportApi.parse.mockResolvedValue(parsed([
      { category: "Alimentation", fromValue: 1, toValue: 3, untilEnd: false, what: "Miettes", details: "", consumption: null, timeSlots: [] },
    ]));
    const onContinue = vi.fn();
    renderScreen({ onContinue });

    const button = screen.getByRole("button", { name: "Continuer" });
    expect(button).toBeDisabled();

    await uploadTo("Protocole", xlsx("protocole.xlsx"));
    await screen.findByText(/Vérifiez les colonnes reconnues/i);
    expect(button).toBeDisabled(); // still gated until confirmation

    await confirmImport();
    await waitFor(() => expect(button).toBeEnabled());

    await userEvent.click(button);
    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  test("can go back to the method choice", async () => {
    const onBack = vi.fn();
    renderScreen({ onBack });
    await userEvent.click(screen.getByRole("button", { name: /Retour/i }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });
});
