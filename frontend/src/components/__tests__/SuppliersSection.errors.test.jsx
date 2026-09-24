import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

// Campaign 3, in the browser: a supplier saved with "contact@" as email showed only
// "Impossible d'enregistrer le fournisseur." — the server's own reason was thrown away.
vi.mock("../../api/endpoints", () => ({ stockApi: { addSupplier: vi.fn(), updateSupplier: vi.fn(), deleteSupplier: vi.fn() } }));
vi.mock("../../context/AuthContext", () => ({ useAuth: () => ({ user: { role: "ADMIN", farm: 1 } }) }));

import SuppliersSection from "../SuppliersSection";
import { stockApi } from "../../api/endpoints";

describe("SuppliersSection — save errors", () => {
  test("the server's field message is shown, not a generic failure", async () => {
    stockApi.addSupplier.mockRejectedValue({ isAxiosError: true, response: { status: 400, data: { email: ["Saisissez une adresse e-mail valide."] } } });
    render(<SuppliersSection suppliers={[]} farmId={1} />);
    await userEvent.click(screen.getByRole("button", { name: /nouveau fournisseur/i }));
    await userEvent.type(screen.getByPlaceholderText("Nom"), "Pharmavet");
    await userEvent.type(screen.getByPlaceholderText("Email"), "contact@");
    await userEvent.click(screen.getByRole("button", { name: /enregistrer|valider|confirmer/i }));
    expect(await screen.findByText("Saisissez une adresse e-mail valide.")).toBeInTheDocument();
  });
});
