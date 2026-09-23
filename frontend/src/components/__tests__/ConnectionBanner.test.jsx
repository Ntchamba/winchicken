import React from "react";
import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

vi.mock("../../api/endpoints", () => ({ farmApi: { exists: vi.fn(() => Promise.resolve({ data: {} })) } }));

import ConnectionBanner from "../ConnectionBanner";
import { reportServerReachable } from "../../pwa/connectivity";

describe("ConnectionBanner", () => {
  afterEach(() => {
    act(() => reportServerReachable(true));
    vi.restoreAllMocks();
  });

  test("hidden while the server answers", () => {
    render(<ConnectionBanner />);
    expect(screen.queryByRole("status")).toBeNull();
  });

  test("shown in French when a request gets no response, gone on the next answer", () => {
    render(<ConnectionBanner />);
    act(() => reportServerReachable(false));
    expect(screen.getByRole("status")).toHaveTextContent("Connexion perdue. Rien ne peut être enregistré pour le moment");
    act(() => reportServerReachable(true));
    expect(screen.queryByRole("status")).toBeNull();
  });

  test("shown when the browser reports the network is gone", () => {
    const onLine = vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    render(<ConnectionBanner />);
    act(() => { window.dispatchEvent(new Event("offline")); });
    expect(screen.getByRole("status")).toBeInTheDocument();
    onLine.mockReturnValue(true);
    act(() => { window.dispatchEvent(new Event("online")); });
    expect(screen.queryByRole("status")).toBeNull();
  });
});
