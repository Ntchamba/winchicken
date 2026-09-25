import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import AssigneePicker, { PICKER_LIMIT } from "../AssigneePicker";
import { tasksApi } from "../../api/endpoints";

// Load test 2026-09-25: every screen with a picker downloaded every account (1 MB at 20 000
// staff). Without a `users` prop the picker loads only when opened, searches server-side, and
// keeps the people already assigned untickable whatever the search says.

vi.mock("../../api/endpoints", () => ({ tasksApi: { assignableUsers: vi.fn() } }));

const EVERYONE = [
  { id: 7, name: "Ouvrier 01" },
  { id: 8, name: "Ouvrier 02" },
  { id: 9, name: "Brice Mbarga" },
];

describe("AssigneePicker without a users list", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    tasksApi.assignableUsers.mockImplementation(({ q }) =>
      Promise.resolve({ data: EVERYONE.filter((u) => u.name.toLowerCase().includes(q.toLowerCase())) }),
    );
  });

  test("asks the server nothing until it is opened, then a limited list", async () => {
    render(<AssigneePicker assignedTo={[]} assignedToNames={[]} onChange={vi.fn()} />);
    expect(tasksApi.assignableUsers).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /Modifier/ }));
    expect(await screen.findByRole("checkbox", { name: "Brice Mbarga" })).toBeInTheDocument();
    expect(tasksApi.assignableUsers).toHaveBeenCalledWith({ q: "", limit: PICKER_LIMIT });
  });

  test("typing searches on the server and the assigned person stays listed", async () => {
    render(<AssigneePicker assignedTo={[7]} assignedToNames={["Ouvrier 01"]} onChange={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /Modifier/ }));
    await screen.findByRole("checkbox", { name: "Brice Mbarga" });
    await userEvent.type(screen.getByRole("searchbox", { name: "Rechercher un employé" }), "brice");
    await waitFor(() => expect(tasksApi.assignableUsers).toHaveBeenLastCalledWith({ q: "brice", limit: PICKER_LIMIT }));
    await waitFor(() => expect(screen.queryByRole("checkbox", { name: "Ouvrier 02" })).not.toBeInTheDocument());
    expect(screen.getByRole("checkbox", { name: "Brice Mbarga" })).not.toBeChecked();
    // Live QA 2026-09-25: the assigned person vanished from a search that did not match them,
    // so they could not be unticked without clearing the search first.
    expect(screen.getByRole("checkbox", { name: "Ouvrier 01" })).toBeChecked();
  });

  test("ticking a found name sends the whole set", async () => {
    const onChange = vi.fn().mockResolvedValue(undefined);
    render(<AssigneePicker assignedTo={[7]} assignedToNames={["Ouvrier 01"]} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: /Modifier/ }));
    await userEvent.click(await screen.findByRole("checkbox", { name: "Brice Mbarga" }));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith([7, 9]));
  });

  test("a full page says the list is cut", async () => {
    tasksApi.assignableUsers.mockResolvedValue({
      data: Array.from({ length: PICKER_LIMIT }, (_, i) => ({ id: 100 + i, name: `Employé ${i}` })),
    });
    render(<AssigneePicker assignedTo={[]} assignedToNames={[]} onChange={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /Modifier/ }));
    expect(await screen.findByText(/Seuls les 50 premiers noms sont affichés/)).toBeInTheDocument();
  });

  test("a failed load is said, not shown as an empty farm", async () => {
    tasksApi.assignableUsers.mockRejectedValue(new Error("réseau"));
    render(<AssigneePicker assignedTo={[]} assignedToNames={[]} onChange={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /Modifier/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Le serveur est inaccessible. Vérifiez votre connexion et réessayez.");
    expect(screen.queryByText("Aucun compte à assigner.")).not.toBeInTheDocument();
  });
});
