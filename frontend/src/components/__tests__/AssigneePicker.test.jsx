import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";
import AssigneePicker from "../AssigneePicker";

// FIX 7 — a protocol line carries a set of workers. What matters here is that every toggle
// sends the *whole* set (the endpoint `set()`s it, so anything else could drift from the
// checkboxes the user sees), and that a rejected save says so instead of looking like it worked.

const USERS = [
  { id: 7, name: "Ouvrier 01" },
  { id: 8, name: "Ouvrier 02" },
  { id: 9, name: "Ouvrier 03" },
];

const open = async () => userEvent.click(screen.getByRole("button", { name: /Modifier/ }));

describe("AssigneePicker", () => {
  test("summarises who is assigned without opening the list", () => {
    render(
      <AssigneePicker users={USERS} assignedTo={[7, 8]} assignedToNames={["Ouvrier 01", "Ouvrier 02"]}
        onChange={vi.fn()} />,
    );
    expect(screen.getByText("Assignée à Ouvrier 01, Ouvrier 02")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  test("an unassigned line says so", () => {
    render(<AssigneePicker users={USERS} assignedTo={[]} assignedToNames={[]} onChange={vi.fn()} />);
    expect(screen.getByText("Non assignée")).toBeInTheDocument();
  });

  test("checking a worker sends the existing set plus that worker", async () => {
    const onChange = vi.fn().mockResolvedValue(undefined);
    render(
      <AssigneePicker users={USERS} assignedTo={[7]} assignedToNames={["Ouvrier 01"]}
        onChange={onChange} />,
    );
    await open();
    await userEvent.click(screen.getByRole("checkbox", { name: "Ouvrier 03" }));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith([7, 9]));
  });

  test("unchecking a worker sends the set without them, not a clear", async () => {
    const onChange = vi.fn().mockResolvedValue(undefined);
    render(
      <AssigneePicker users={USERS} assignedTo={[7, 8]} assignedToNames={["Ouvrier 01", "Ouvrier 02"]}
        onChange={onChange} />,
    );
    await open();
    await userEvent.click(screen.getByRole("checkbox", { name: "Ouvrier 01" }));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith([8]));
  });

  test("a rejected save shows a French error instead of a silent no-op", async () => {
    const onChange = vi.fn().mockRejectedValue(new Error("boom"));
    render(<AssigneePicker users={USERS} assignedTo={[]} assignedToNames={[]} onChange={onChange} />);
    await open();
    await userEvent.click(screen.getByRole("checkbox", { name: "Ouvrier 02" }));
    expect(await screen.findByText("L'affectation n'a pas été enregistrée. Réessayez.")).toBeInTheDocument();
  });

  test("a successful save confirms, so a phone tap is never ambiguous", async () => {
    const onChange = vi.fn().mockResolvedValue(undefined);
    render(<AssigneePicker users={USERS} assignedTo={[]} assignedToNames={[]} onChange={onChange} />);
    await open();
    await userEvent.click(screen.getByRole("checkbox", { name: "Ouvrier 02" }));
    expect(await screen.findByText("Affectation enregistrée.")).toBeInTheDocument();
  });

  test("marks the logged-in user's own assignment", () => {
    render(
      <AssigneePicker users={USERS} assignedTo={[7]} assignedToNames={["Ouvrier 01"]}
        currentUserId={7} onChange={vi.fn()} />,
    );
    expect(screen.getByText("Assignée à Ouvrier 01 (vous)")).toBeInTheDocument();
  });
});
