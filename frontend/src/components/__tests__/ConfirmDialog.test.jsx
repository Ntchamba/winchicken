import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import ConfirmDialog from "../ConfirmDialog";

// FIX 8 group 6: every destructive action behind this dialog (clôture/suppression de bande,
// suppression de catégorie) swallowed its rejection. The dialog is the one place the user is
// looking when the action fails, so the error slot lives here rather than in each caller.

describe("ConfirmDialog", () => {
  test("shows the failure of the confirmed action, next to the button that ran it", () => {
    render(
      <ConfirmDialog
        message="Supprimer cette bande est définitif. Continuer ?"
        confirmLabel="Supprimer définitivement"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
        error="Cette bande n'a pas pu être supprimée."
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Cette bande n'a pas pu être supprimée.");
    expect(screen.getByRole("button", { name: "Supprimer définitivement" })).toBeEnabled();
  });

  test("renders no alert region when nothing has failed", () => {
    render(<ConfirmDialog message="Continuer ?" onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
