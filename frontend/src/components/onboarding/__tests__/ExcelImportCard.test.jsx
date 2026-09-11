import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";
import ExcelImportCard from "../ExcelImportCard";

const xlsx = () =>
  new File(["x"], "protocole.xlsx", {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });

describe("ExcelImportCard", () => {
  test("hands the picked file to onImport and links the template", async () => {
    const user = userEvent.setup();
    const onImport = vi.fn();
    const { container } = render(
      <ExcelImportCard title="Protocole" hint="Aliments, soins, créneaux" templateUrl="http://test/t.xlsx" onImport={onImport} />,
    );

    expect(screen.getByRole("link", { name: /Télécharger un modèle/i })).toHaveAttribute("href", "http://test/t.xlsx");

    const file = xlsx();
    await user.upload(container.querySelector('input[type="file"]'), file);
    expect(onImport).toHaveBeenCalledWith(file);
  });

  test("blocks a second pick while an import is in flight", () => {
    render(<ExcelImportCard title="Stock" hint="Articles" templateUrl="http://test/s.xlsx" onImport={() => {}} importing />);
    expect(screen.getByRole("button", { name: /Importer un fichier/i })).toBeDisabled();
  });

  // The Finances import has no backend endpoint yet — the card is shown so the screen reads
  // as complete, but nothing about it is operable.
  test("a disabled card shows its badge, no template link and no file input", () => {
    const { container } = render(
      <ExcelImportCard title="Finances" hint="Recettes et dépenses" badge="Bientôt disponible" disabled />,
    );

    expect(screen.getByText("Bientôt disponible")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Importer un fichier/i })).toBeDisabled();
    expect(screen.queryByRole("link", { name: /Télécharger un modèle/i })).not.toBeInTheDocument();
    expect(container.querySelector('input[type="file"]')).toBeNull();
  });
});
