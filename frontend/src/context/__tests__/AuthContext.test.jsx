import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { AuthProvider, useAuth } from "../AuthContext";
import ProtectedRoute from "../../routes/ProtectedRoute";
import { authApi } from "../../api/endpoints";

// 2026-09-25 (phone usability audit): opening the app on a slow farm connection showed a bare
// "Chargement…" for as long as /auth/me took, and any failed /auth/me — a dropped connection
// included — logged the worker out.

vi.mock("../../api/endpoints", () => ({ authApi: { me: vi.fn() } }));

const USER = { id: 7, name: "Awa", role: "WORKER", is_configured: true };
const TOKENS = JSON.stringify({ access: "a", refresh: "r" });

function Who() {
  const { user } = useAuth();
  return <p>Connecté : {user?.name}</p>;
}

const app = () => render(
  <AuthProvider>
    <MemoryRouter initialEntries={["/dashboard"]}>
      <Routes>
        <Route path="/login" element={<p>Page de connexion</p>} />
        <Route element={<ProtectedRoute />}>
          <Route path="/dashboard" element={<Who />} />
        </Route>
      </Routes>
    </MemoryRouter>
  </AuthProvider>,
);

describe("AuthProvider on a poor connection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  test("a returning user's app opens at once, before /auth/me answers", async () => {
    localStorage.setItem("winchicken_tokens", TOKENS);
    localStorage.setItem("winchicken_user", JSON.stringify(USER));
    authApi.me.mockReturnValue(new Promise(() => {}));
    app();
    expect(screen.getByText("Connecté : Awa")).toBeInTheDocument();
  });

  test("a dropped connection keeps the user logged in", async () => {
    localStorage.setItem("winchicken_tokens", TOKENS);
    localStorage.setItem("winchicken_user", JSON.stringify(USER));
    authApi.me.mockRejectedValue(new Error("Network Error"));
    app();
    await waitFor(() => expect(authApi.me).toHaveBeenCalled());
    expect(screen.getByText("Connecté : Awa")).toBeInTheDocument();
    expect(localStorage.getItem("winchicken_tokens")).toBe(TOKENS);
  });

  test("the server refusing the session logs out and forgets the saved profile", async () => {
    localStorage.setItem("winchicken_tokens", TOKENS);
    localStorage.setItem("winchicken_user", JSON.stringify(USER));
    authApi.me.mockRejectedValue({ response: { status: 401 } });
    app();
    expect(await screen.findByText("Page de connexion")).toBeInTheDocument();
    expect(localStorage.getItem("winchicken_tokens")).toBeNull();
    expect(localStorage.getItem("winchicken_user")).toBeNull();
  });

  test("first start with no server: a way out, not a login form or a bare loader", async () => {
    localStorage.setItem("winchicken_tokens", TOKENS);
    authApi.me.mockRejectedValue(new Error("Network Error"));
    app();
    expect(await screen.findByText(/Le serveur de la ferme ne répond pas/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Réessayer" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Se déconnecter" })).toBeInTheDocument();
    expect(screen.queryByText("Page de connexion")).not.toBeInTheDocument();
  });
});
