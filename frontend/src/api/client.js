import axios from "axios";
import { reportServerReachable } from "../pwa/connectivity";

export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

const client = axios.create({ baseURL: API_URL });

// A corrupted entry (or storage the browser refuses) reads as "logged out": throwing here would
// throw from the request interceptor and fail every API call, the login included.
export function getTokens() {
  try {
    const raw = localStorage.getItem("winchicken_tokens");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setTokens(tokens) {
  if (tokens) localStorage.setItem("winchicken_tokens", JSON.stringify(tokens));
  else localStorage.removeItem("winchicken_tokens");
}

client.interceptors.request.use((config) => {
  const tokens = getTokens();
  if (tokens?.access) config.headers.Authorization = `Bearer ${tokens.access}`;
  return config;
});

let refreshPromise = null;

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    if (error.response?.status !== 401 || original._retried) {
      return Promise.reject(error);
    }
    const tokens = getTokens();
    if (!tokens?.refresh) {
      setTokens(null);
      return Promise.reject(error);
    }
    original._retried = true;
    try {
      // `_retried` on the refresh call itself: an expired refresh token makes it 401 too, and
      // without the flag that 401 re-entered this interceptor, awaited `refreshPromise` — i.e.
      // itself — and never settled, leaving the app on its loading screen for good.
      refreshPromise =
        refreshPromise || client.post("/auth/refresh/", { refresh: tokens.refresh }, { _retried: true });
      const { data } = await refreshPromise;
      refreshPromise = null;
      setTokens({ ...tokens, access: data.access });
      original.headers.Authorization = `Bearer ${data.access}`;
      // Awaited here (not `return client(original)`) so a retry that still 401s — e.g. the
      // refresh token itself is still cryptographically valid but the user row behind it is
      // gone, as after a factory reset (apps.core.services.factory_reset_farm): SimpleJWT's
      // TokenRefreshView never touches the User table, so the refresh above "succeeds" and
      // hands back a token for a user that no longer exists — falls into the same catch below
      // instead of rejecting silently past it, which a bare `return` would have done (a
      // `return`ed promise's rejection isn't caught by this try/catch).
      return await client(original);
    } catch (refreshError) {
      refreshPromise = null;
      setTokens(null);
      // "/" (the landing page), not "/login": it re-checks GET /api/farm/exists/ on its own and
      // shows "Créer la ferme" instead of "Se connecter" when the farm is gone (factory reset)
      // — "/login" has no such check and would offer a login form for a farm that no longer
      // exists. For the ordinary token-expiry case this costs one extra click, not a break.
      window.location.href = "/";
      return Promise.reject(refreshError);
    }
  }
);

// Connectivity for the "connexion perdue" banner (src/pwa/connectivity.js): any response —
// even a 4xx/5xx — means the server answered; no response at all (and not a cancel) means it
// did not. Observes only; the error still reaches the caller unchanged.
client.interceptors.response.use(
  (response) => {
    reportServerReachable(true);
    return response;
  },
  (error) => {
    if (error.response) reportServerReachable(true);
    else if (!axios.isCancel(error)) reportServerReachable(false);
    return Promise.reject(error);
  }
);

export default client;
