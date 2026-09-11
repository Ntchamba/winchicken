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

  test("imports a protocol file and hands the resolved rows up, categories included", async () => {
    protocolImportApi.parse.mockResolvedValue({
      data: {
        imported: 2,
        skipped: [],
        warnings: [],
        rows: [
          { category: "Alimentation", fromValue: 1, toValue: 10, untilEnd: false, what: "Démarrage", details: "", consumption: null, timeSlots: [{ startTime: "07:00", endTime: "09:00" }] },
          { category: "Biosécurité", fromValue: 1, toValue: 5, untilEnd: false, what: "Pédiluve", details: "", consumption: null, timeSlots: [] },
        ],
      },
    });
    const onProtocolImported = vi.fn();
    renderScreen({ onProtocolImported });

    await uploadTo("Protocole", xlsx("protocole.xlsx"));

    await waitFor(() => expect(onProtocolImported).toHaveBeenCalledTimes(1));
    const [categories, schedules] = onProtocolImported.mock.calls[0];

    // The 5 backend defaults keep their positions; the file's own category is appended after
    // them — buildOnboardingRequest slices at 5 to find the custom ones.
    expect(categories.slice(0, 5).map((c) => c.label)).toEqual([
      "Alimentation", "Température", "Santé et soins", "Vaccination", "Nettoyage",
    ]);
    expect(categories[5]).toMatchObject({ label: "Biosécurité" });

    // Both rows landed, under their own category, and the time slot survived.
    const allRows = Object.values(schedules).flat();
    expect(allRows).toHaveLength(2);
    expect(schedules["default-0"][0]).toMatchObject({ what: "Démarrage" });
    expect(schedules["default-0"][0].timeSlots[0]).toMatchObject({ startTime: "07:00", endTime: "09:00" });
    expect(schedules[categories[5].id][0]).toMatchObject({ what: "Pédiluve" });

    expect(await screen.findByText(/2 lignes importées/i)).toBeInTheDocument();
  });

  test("a protocol file with no usable row reports the skips and does not unlock 'Continuer'", async () => {
    protocolImportApi.parse.mockResolvedValue({
      data: { imported: 0, skipped: [{ line: 2, reason: "Catégorie inconnue" }], warnings: [], rows: [] },
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

  test("imports a stock file through the update-or-create importer and shows its summary", async () => {
    stockApi.importXlsx.mockResolvedValue({ data: { updated: 3, created: 2, skipped: [] } });
    renderScreen();

    const file = xlsx("stock.xlsx");
    await uploadTo("Stock", file);

    await waitFor(() => expect(stockApi.importXlsx).toHaveBeenCalledWith(1, file));
    expect(await screen.findByText(/3 mises à jour, 2 créées, 0 ignorée/i)).toBeInTheDocument();
  });

  // No finance import endpoint exists (apps/finance/urls.py has none), so the card must be
  // visible but inert — and must not block the rest of the flow.
  test("the Finances card is present but inert", async () => {
    renderScreen();
    // Let the on-mount stock fetch settle before asserting, so its setState isn't left
    // dangling outside act().
    await waitFor(() => expect(stockApi.items).toHaveBeenCalled());
    const finances = cardFor("Finances");

    expect(within(finances).getByText("Bientôt disponible")).toBeInTheDocument();
    expect(within(finances).getByRole("button", { name: /Importer un fichier/i })).toBeDisabled();
    expect(finances.querySelector('input[type="file"]')).toBeNull();
  });

  test("'Continuer' only unlocks after a successful protocol import", async () => {
    protocolImportApi.parse.mockResolvedValue({
      data: {
        imported: 1, skipped: [], warnings: [],
        rows: [{ category: "Alimentation", fromValue: 1, toValue: 3, untilEnd: false, what: "Miettes", details: "", consumption: null, timeSlots: [] }],
      },
    });
    const onContinue = vi.fn();
    renderScreen({ onContinue });

    const button = screen.getByRole("button", { name: "Continuer" });
    expect(button).toBeDisabled();

    await uploadTo("Protocole", xlsx("protocole.xlsx"));
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
