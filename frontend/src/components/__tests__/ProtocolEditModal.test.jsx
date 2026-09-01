import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import ProtocolEditModal from "../ProtocolEditModal";
import { batchesApi, housesApi, stockApi } from "../../api/endpoints";
import { useHousesContext } from "../../context/HousesContext";

// Regression test for the sidebar-staleness bug (docs/deviations.md Parts 5/6, Part 15/Part B):
// batch renames and other protocol-edit saves used to leave the sidebar showing stale
// house/batch names because nothing told it to refetch. The eventual root-cause fix was
// ProtocolEditModal calling useHousesContext().refetch() directly on every save, rather than
// depending on each page remembering to wire a refresh callback. This test pins that call down
// so a future edit can't quietly drop it again.
//
// HouseProtocolForm is mocked out: the regression lives entirely in ProtocolEditModal's own
// save-handling logic, not in the form's internals, and the form is a large, separately-tested
// surface (see HouseProtocolForm.test.jsx) that would only add unrelated setup here.

vi.mock("../../api/endpoints", () => ({
  housesApi: {
    listProtocolCategories: vi.fn(),
    getProtocol: vi.fn(),
    detail: vi.fn(),
    putProtocol: vi.fn(),
    update: vi.fn(),
  },
  batchesApi: {
    list: vi.fn(),
    quickEdit: vi.fn(),
  },
  stockApi: {
    items: vi.fn(),
  },
}));

vi.mock("../../context/HousesContext", () => ({
  useHousesContext: vi.fn(),
}));

vi.mock("../../context/AuthContext", () => ({
  useAuth: () => ({ user: { farm: 1 } }),
}));

const formProps = vi.fn();
vi.mock("../HouseProtocolForm", () => ({
  default: (props) => {
    formProps(props);
    return (
      <button
        onClick={() =>
          props.onSave({
            protocolLines: [],
            batchName: "Bande Renommée",
            weighingFrequency: null,
            house: { buildingName: "Bâtiment Renommé" },
          })
        }
      >
        Fake Save
      </button>
    );
  },
}));

describe("ProtocolEditModal — sidebar staleness regression", () => {
  const refetchHouses = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    useHousesContext.mockReturnValue({ refetch: refetchHouses });
    housesApi.listProtocolCategories.mockResolvedValue({ data: [] });
    housesApi.getProtocol.mockResolvedValue({ data: [] });
    housesApi.detail.mockResolvedValue({ data: { name: "Bâtiment Test" } });
    batchesApi.list.mockResolvedValue({
      data: [{ batch_code: "B-1", status: "ACTIVE", name: "Ancien Nom" }],
    });
    housesApi.putProtocol.mockResolvedValue({ data: [] });
    housesApi.update.mockResolvedValue({ data: {} });
    batchesApi.quickEdit.mockResolvedValue({ data: {} });
    stockApi.items.mockResolvedValue({ data: { items: [] } });
  });

  test("loads the existing protocol into the form in management mode (no wizard chrome)", async () => {
    housesApi.getProtocol.mockResolvedValue({
      data: [{
        id: 9, category: 3, from_value: 1, from_unit: "DAY", to_value: 5, to_unit: "DAY",
        until_end: false, what: "Aliment démarrage", details: "", time_slots: [],
      }],
    });
    housesApi.listProtocolCategories.mockResolvedValue({ data: [{ id: 3, label: "Alimentation", icon: "Soup" }] });

    render(<ProtocolEditModal houseCode="H-1" onClose={() => {}} onSaved={() => {}} />);
    await screen.findByText("Fake Save");

    const props = formProps.mock.calls.at(-1)[0];
    expect(props.mode).toBe("management");            // never "onboarding"
    expect(props.onBack).toBeUndefined();             // wizard "Retour" wiring not passed
    expect(props.initialSchedules[3]).toHaveLength(1); // fetched line is pre-loaded, not empty
    expect(props.initialSchedules[3][0].what).toBe("Aliment démarrage");
  });

  test("saving refetches the shared houses/batches list", async () => {
    render(<ProtocolEditModal houseCode="H-1" onClose={() => {}} onSaved={() => {}} />);

    const saveButton = await screen.findByText("Fake Save");
    await userEvent.click(saveButton);

    await waitFor(() => expect(refetchHouses).toHaveBeenCalledTimes(1));
    // The renamed batch is what actually reaches the server — the sidebar can only stop being
    // stale if it refetches *after* this resolves, not before.
    expect(batchesApi.quickEdit).toHaveBeenCalledWith("B-1", { name: "Bande Renommée" });
  });

  test("a changed house name is persisted via PATCH /houses/{code}/ (was a silent no-op)", async () => {
    render(<ProtocolEditModal houseCode="H-1" onClose={() => {}} onSaved={() => {}} />);
    await userEvent.click(await screen.findByText("Fake Save"));
    await waitFor(() =>
      expect(housesApi.update).toHaveBeenCalledWith("H-1", { name: "Bâtiment Renommé" }),
    );
  });

  test("an unchanged / blank house name is not PATCHed", async () => {
    housesApi.detail.mockResolvedValue({ data: { name: "Bâtiment Renommé" } }); // already equals what the form sends
    render(<ProtocolEditModal houseCode="H-1" onClose={() => {}} onSaved={() => {}} />);
    await userEvent.click(await screen.findByText("Fake Save"));
    await waitFor(() => expect(refetchHouses).toHaveBeenCalled());
    expect(housesApi.update).not.toHaveBeenCalled();
  });
});
