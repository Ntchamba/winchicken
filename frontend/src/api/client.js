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

// The last profile /auth/me returned (context/AuthContext.jsx), so the app can open on a slow
// connection without waiting for it. Belongs to the session: it goes when the tokens go.
export const USER_CACHE_KEY = "winchicken_user";

export function setTokens(tokens) {
  if (tokens) localStorage.setItem("winchicken_tokens", JSON.stringify(tokens));
  else {
    localStorage.removeItem("winchicken_tokens");
    localStorage.removeItem(USER_CACHE_KEY);
  }
}

client.interceptors.request.use((config) => {
  const tokens = getTokens();
  if (tokens?.access) config.headers.Authorization = `Bearer ${tokens.access}`;
  return config;
});

// A double-tapped submit fires the same write twice in one tick, before React has re-rendered
// the button as disabled: a stock "Ajouter" recorded two IN movements (and, with a price, two
// expenses) live (campaign 9, finding B14). Rather than a guard in every form, an *identical*
// write — same method, URL and serialized body — made while the first is still in flight gets
// the first one's promise instead of reaching the server again. Reads are never coalesced; a
// write that has answered (success or error) is released, so a deliberate retry goes through;
// a non-string body (a file upload) is left alone.
const inFlightWrites = new Map();

function coalescing(adapter) {
  if (adapter?.coalescing) return adapter; // the 401 retry re-sends an already wrapped config
  const send = axios.getAdapter(adapter);
  const wrapped = (config) => {
    const method = (config.method || "get").toLowerCase();
    if (method === "get" || method === "head" || method === "options" || typeof config.data !== "string") {
      return send(config);
    }
    const key = `${method} ${config.baseURL || ""}${config.url} ${config.data}`;
    const pending = inFlightWrites.get(key);
    if (pending) return pending;
    const request = Promise.resolve(send(config)).finally(() => inFlightWrites.delete(key));
    inFlightWrites.set(key, request);
    return request;
  };
  wrapped.coalescing = true;
  return wrapped;
}

client.interceptors.request.use((config) => {
  config.adapter = coalescing(config.adapter);
  return config;
});

let refreshPromise = null;

// "/" (the landing page), not "/login": it re-checks GET /api/farm/exists/ on its own and shows
// "Créer la ferme" instead of "Se connecter" when the farm is gone (factory reset) — "/login"
// has no such check and would offer a login form for a farm that no longer exists. For the
// ordinary token-expiry case this costs one extra click, not a break.
function endSession(error) {
  setTokens(null);
  window.location.href = "/";
  return Promise.reject(error);
}

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
    let access;
    try {
      // `_retried` on the refresh call itself: an expired refresh token makes it 401 too, and
      // without the flag that 401 re-entered this interceptor, awaited `refreshPromise` — i.e.
      // itself — and never settled, leaving the app on its loading screen for good.
      refreshPromise =
        refreshPromise || client.post("/auth/refresh/", { refresh: tokens.refresh }, { _retried: true });
      ({ data: { access } } = await refreshPromise);
      refreshPromise = null;
    } catch (refreshError) {
      refreshPromise = null;
      return endSession(refreshError);
    }
    setTokens({ ...tokens, access });
    original.headers.Authorization = `Bearer ${access}`;
    try {
      return await client(original);
    } catch (retryError) {
      // Only a retry that is *still* 401 ends the session: the refresh token is valid but the
      // user row behind it is gone, as after a factory reset (apps.core.services.
      // factory_reset_farm — SimpleJWT's TokenRefreshView never touches the User table, so the
      // refresh "succeeds"). Any other failure is the request's own answer — a 400 on a save
      // made just after the access token expired used to log the user out.
      if (retryError.response?.status === 401) return endSession(retryError);
      return Promise.reject(retryError);
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
