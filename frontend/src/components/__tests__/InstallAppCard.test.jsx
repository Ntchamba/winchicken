import React from "react";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";
import InstallAppCard from "../InstallAppCard";

// The module listens from import time, as it does in the app (main.jsx imports it first).
function fireInstallPrompt(outcome) {
  const event = new Event("beforeinstallprompt", { cancelable: true });
  event.prompt = vi.fn();
  event.userChoice = Promise.resolve({ outcome });
  act(() => { window.dispatchEvent(event); });
  return event;
}

describe("InstallAppCard", () => {
  test("without the browser's install event, explains the manual route in French", () => {
    render(<InstallAppCard />);
    expect(screen.queryByRole("button", { name: /installer l'application/i })).toBeNull();
    expect(screen.getByText(/ne propose pas l'installation pour le moment/)).toBeInTheDocument();
  });

  test("the button opens the browser's own dialog; a dismissal says it can be retried", async () => {
    const user = userEvent.setup();
    const event = fireInstallPrompt("dismissed");
    expect(event.defaultPrevented).toBe(true); // no automatic Chrome mini-bar
    render(<InstallAppCard />);
    await user.click(screen.getByRole("button", { name: /installer l'application/i }));
    expect(event.prompt).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("status")).toHaveTextContent("Installation annulée");
  });

  test("after installation it confirms instead of offering the button again", () => {
    fireInstallPrompt("accepted");
    render(<InstallAppCard />);
    act(() => { window.dispatchEvent(new Event("appinstalled")); });
    expect(screen.getByText(/Winchicken est installée sur cet appareil/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /installer l'application/i })).toBeNull();
  });
});
