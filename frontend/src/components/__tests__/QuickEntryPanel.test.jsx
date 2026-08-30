import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import QuickEntryPanel from "../QuickEntryPanel";
import { batchesApi } from "../../api/endpoints";

// QuickEntryPanel upserts mortality and eggs into DailyLog independently: a field left blank is
// sent as `null`, which the backend reads as "leave this one alone". This pins that down —
// logging mortality must not clobber eggs already recorded for the day, and vice versa.

vi.mock("../../api/endpoints", () => ({
  batchesApi: { quickEntry: vi.fn() },
}));

const MORTALITY = "Mortalité — signal de perte";
const EGGS = "Œufs collectés";

describe("QuickEntryPanel — independent mortality / eggs upsert", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    batchesApi.quickEntry.mockResolvedValue({
      data: { mortality: 7, cumulativeMortalityPct: null, mortalityReferenceRange: null },
    });
  });

  const renderPanel = () =>
    render(<QuickEntryPanel batches={[{ batch_code: "B-1", name: "Bande" }]} />);

  test("submitting only mortality sends eggsCollected: null", async () => {
    renderPanel();
    await userEvent.type(screen.getByLabelText(MORTALITY), "7");
    await userEvent.click(screen.getByRole("button", { name: /enregistrer/i }));

    await waitFor(() => expect(batchesApi.quickEntry).toHaveBeenCalledTimes(1));
    const [code, payload] = batchesApi.quickEntry.mock.calls[0];
    expect(code).toBe("B-1");
    expect(payload.mortality).toBe(7);
    expect(payload.eggsCollected).toBeNull();
  });

  test("submitting only eggs sends mortality: null", async () => {
    renderPanel();
    await userEvent.type(screen.getByLabelText(EGGS), "12");
    await userEvent.click(screen.getByRole("button", { name: /enregistrer/i }));

    await waitFor(() => expect(batchesApi.quickEntry).toHaveBeenCalledTimes(1));
    const [, payload] = batchesApi.quickEntry.mock.calls[0];
    expect(payload.eggsCollected).toBe(12);
    expect(payload.mortality).toBeNull();
  });

  test("both fields clear after a successful save so the next entry starts fresh", async () => {
    renderPanel();
    await userEvent.type(screen.getByLabelText(MORTALITY), "3");
    await userEvent.type(screen.getByLabelText(EGGS), "9");
    await userEvent.click(screen.getByRole("button", { name: /enregistrer/i }));

    await waitFor(() => expect(screen.getByLabelText(MORTALITY)).toHaveValue(null));
    expect(screen.getByLabelText(EGGS)).toHaveValue(null);
  });
});
