import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, test, vi } from "vitest";
import SettingsPage from "../SettingsPage";
import useWebPush from "../../../hooks/useWebPush";

// Pins the browser-notification opt-in contract: requestPermission() is reached ONLY from the
// visible control's click (never on mount), and the card renders the real permission state —
// actionable for "default", success for "granted", unblock steps for "denied".

vi.mock("../../../hooks/useWebPush", () => ({ default: vi.fn() }));
vi.mock("../../../hooks/useDocumentTitle", () => ({ default: vi.fn() }));
vi.mock("../../../components/FactoryResetModal", () => ({ default: () => null }));
vi.mock("../../../context/AuthContext", () => ({
  useAuth: () => ({
    user: { name: "A", email: "a@b.c", role: "WORKER", farm_name: "F" },
  }),
}));

const base = {
  supported: true, enabled: true, subscribed: false, busy: false, error: "",
  permission: "default", enable: vi.fn(), disable: vi.fn(),
};

describe("SettingsPage — notifications bureau", () => {
  beforeEach(() => vi.clearAllMocks());

  test("does not request permission on mount", () => {
    const enable = vi.fn();
    useWebPush.mockReturnValue({ ...base, enable });
    render(<SettingsPage />);
    expect(enable).not.toHaveBeenCalled();
  });

  test("'default' shows an actionable button that calls enable() on click", async () => {
    const enable = vi.fn();
    useWebPush.mockReturnValue({ ...base, permission: "default", enable });
    render(<SettingsPage />);
    const btn = screen.getByRole("button", { name: "Activer les notifications" });
    await userEvent.click(btn);
    expect(enable).toHaveBeenCalledTimes(1);
  });

  test("'granted' shows the success state and no opt-in button", () => {
    useWebPush.mockReturnValue({ ...base, permission: "granted" });
    render(<SettingsPage />);
    expect(screen.getByText(/Notifications activées/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Activer les notifications" })).toBeNull();
  });

  test("'denied' explains how to unblock via browser settings", () => {
    useWebPush.mockReturnValue({ ...base, permission: "denied" });
    render(<SettingsPage />);
    expect(screen.getByText("Notifications bloquées par le navigateur")).toBeInTheDocument();
    expect(screen.getByText(/l'icône du site à gauche de la barre d'adresse/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Activer les notifications" })).toBeNull();
  });
});
