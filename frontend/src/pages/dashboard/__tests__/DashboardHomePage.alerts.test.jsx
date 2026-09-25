import React from "react";
import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import DashboardHomePage from "../DashboardHomePage";
import { alertsApi } from "../../../api/endpoints";

// Live QA 2026-09-25: the "Alertes ouvertes" tile counted the 6 alerts the card lists, next to a
// health badge counting every open one. The tile now shows the server's total.

vi.mock("../../../api/endpoints", () => ({
  alertsApi: { listOpen: vi.fn() },
  batchesApi: { listActive: vi.fn(() => Promise.resolve({ data: [] })), growthCurves: vi.fn(() => Promise.resolve({ data: [] })) },
}));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn(), useOutletContext: () => ({ houses: [] }) }));
vi.mock("../../../context/AuthContext", () => ({ useAuth: () => ({ user: { farm_name: "Ferme" } }) }));
vi.mock("../../../components/ProtocolEditModal", () => ({ default: () => null }));
const seen = [];
vi.mock("../../../components/HomeDashboard", () => ({
  default: (props) => { seen.push(props); return null; },
}));

describe("DashboardHomePage open alerts", () => {
  beforeEach(() => { seen.length = 0; });

  test("the tile counts every open alert, the card lists six", async () => {
    alertsApi.listOpen.mockResolvedValue({
      data: { count: 46, next: "?page=2", results: Array.from({ length: 20 }, (_, i) => ({ id: i, severity: "warning", message: `A${i}` })) },
    });
    render(<DashboardHomePage />);
    await waitFor(() => expect(seen.at(-1).stats.openAlerts).toBe(46));
    expect(seen.at(-1).alerts).toHaveLength(6);
  });
});
