import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import client, { getTokens, setTokens } from "../client";

// The phone stays logged in for days (REFRESH_TOKEN_LIFETIME = 7 days). When the refresh token
// finally expires, POST /auth/refresh/ answers 401 itself — that 401 goes back through the same
// interceptor, and it must end in "tokens cleared, back to /", not in a request that waits on
// itself forever and leaves the app on its loading screen.

const answer = (config, status, data = {}) => {
  if (status < 400) return Promise.resolve({ data, status, statusText: "", headers: {}, config });
  const error = new Error(`Request failed with status code ${status}`);
  error.config = config;
  error.response = { data, status, statusText: "", headers: {}, config };
  return Promise.reject(error);
};

let routes;
let seen;

beforeEach(() => {
  localStorage.clear();
  seen = [];
  client.defaults.adapter = (config) => {
    seen.push({ url: config.url, auth: config.headers.Authorization });
    const route = routes[config.url];
    return route ? route(config) : answer(config, 404);
  };
  Object.defineProperty(window, "location", { value: { href: "/tableau" }, writable: true, configurable: true });
});

afterEach(() => vi.useRealTimers());

const withTimeout = (promise, ms = 1000) =>
  Promise.race([promise, new Promise((_, reject) => setTimeout(() => reject(new Error("never settled")), ms))]);

describe("api client — tokens", () => {
  test("sends the stored access token as a Bearer header", async () => {
    setTokens({ access: "A1", refresh: "R1" });
    routes = { "/me/": (c) => answer(c, 200, { id: 1 }) };
    await client.get("/me/");
    expect(seen[0].auth).toBe("Bearer A1");
  });

  test("a corrupted token entry reads as logged out instead of breaking every request", async () => {
    localStorage.setItem("winchicken_tokens", "{not json");
    expect(getTokens()).toBeNull();
    routes = { "/farm/exists/": (c) => answer(c, 200, { exists: true }) };
    await expect(client.get("/farm/exists/")).resolves.toMatchObject({ status: 200 });
  });
});

describe("api client — 401 handling", () => {
  test("an expired access token is refreshed once and the request retried with the new one", async () => {
    setTokens({ access: "OLD", refresh: "R1" });
    routes = {
      "/me/": (c) => (c.headers.Authorization === "Bearer NEW" ? answer(c, 200, { id: 1 }) : answer(c, 401)),
      "/auth/refresh/": (c) => answer(c, 200, { access: "NEW" }),
    };
    const res = await client.get("/me/");
    expect(res.data).toEqual({ id: 1 });
    expect(getTokens()).toEqual({ access: "NEW", refresh: "R1" });
  });

  test("two requests failing together share one refresh call", async () => {
    setTokens({ access: "OLD", refresh: "R1" });
    routes = {
      "/a/": (c) => (c.headers.Authorization === "Bearer NEW" ? answer(c, 200) : answer(c, 401)),
      "/b/": (c) => (c.headers.Authorization === "Bearer NEW" ? answer(c, 200) : answer(c, 401)),
      "/auth/refresh/": (c) => answer(c, 200, { access: "NEW" }),
    };
    await Promise.all([client.get("/a/"), client.get("/b/")]);
    expect(seen.filter((s) => s.url === "/auth/refresh/")).toHaveLength(1);
  });

  test("an expired refresh token clears the session and goes to / — it does not hang", async () => {
    setTokens({ access: "OLD", refresh: "EXPIRED" });
    routes = {
      "/me/": (c) => answer(c, 401),
      "/auth/refresh/": (c) => answer(c, 401, { code: "token_not_valid" }),
    };
    await expect(withTimeout(client.get("/me/"))).rejects.toMatchObject({ response: { status: 401 } });
    expect(getTokens()).toBeNull();
    expect(window.location.href).toBe("/");
  });

  test("after an expired refresh, the next login's 401 refreshes again instead of reusing the dead call", async () => {
    setTokens({ access: "OLD", refresh: "EXPIRED" });
    routes = { "/me/": (c) => answer(c, 401), "/auth/refresh/": (c) => answer(c, 401) };
    await withTimeout(client.get("/me/")).catch(() => {});

    setTokens({ access: "OLD2", refresh: "R2" });
    routes = {
      "/me/": (c) => (c.headers.Authorization === "Bearer NEW2" ? answer(c, 200) : answer(c, 401)),
      "/auth/refresh/": (c) => answer(c, 200, { access: "NEW2" }),
    };
    await expect(withTimeout(client.get("/me/"))).resolves.toMatchObject({ status: 200 });
  });

  // Campaign 3, in the browser: a save made just after the access token expired was refreshed
  // and retried, the retry answered 400 (a validation error) — and the user was logged out,
  // because every retry failure fell into the "refresh failed" branch.
  test("a retry that answers 400 returns the 400 and keeps the session", async () => {
    setTokens({ access: "OLD", refresh: "R1" });
    routes = {
      "/save/": (c) => (c.headers.Authorization === "Bearer NEW" ? answer(c, 400, { detail: "Poids invalide." }) : answer(c, 401)),
      "/auth/refresh/": (c) => answer(c, 200, { access: "NEW" }),
    };
    await expect(client.put("/save/", {})).rejects.toMatchObject({ response: { status: 400, data: { detail: "Poids invalide." } } });
    expect(getTokens()).toEqual({ access: "NEW", refresh: "R1" });
    expect(window.location.href).toBe("/tableau");
  });

  test("a retry that still answers 401 (user gone after a factory reset) logs out", async () => {
    setTokens({ access: "OLD", refresh: "R1" });
    routes = { "/me/": (c) => answer(c, 401), "/auth/refresh/": (c) => answer(c, 200, { access: "NEW" }) };
    await expect(withTimeout(client.get("/me/"))).rejects.toMatchObject({ response: { status: 401 } });
    expect(getTokens()).toBeNull();
    expect(window.location.href).toBe("/");
  });

  test("a 401 with no refresh token clears the session without calling refresh", async () => {
    setTokens({ access: "OLD" });
    routes = { "/me/": (c) => answer(c, 401) };
    await expect(client.get("/me/")).rejects.toMatchObject({ response: { status: 401 } });
    expect(getTokens()).toBeNull();
    expect(seen.map((s) => s.url)).toEqual(["/me/"]);
  });

  test("a wrong password on login (401 with no session) is returned to the form as is", async () => {
    routes = { "/auth/login/": (c) => answer(c, 401, { detail: "Identifiants invalides" }) };
    await expect(client.post("/auth/login/", {})).rejects.toMatchObject({ response: { status: 401 } });
    expect(window.location.href).toBe("/tableau");
  });

  test("other errors pass through untouched", async () => {
    setTokens({ access: "A1", refresh: "R1" });
    routes = { "/x/": (c) => answer(c, 500) };
    await expect(client.get("/x/")).rejects.toMatchObject({ response: { status: 500 } });
    expect(getTokens()).toEqual({ access: "A1", refresh: "R1" });
  });
});
