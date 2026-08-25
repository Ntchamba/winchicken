import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

const client = axios.create({ baseURL: API_URL });

export function getTokens() {
  const raw = localStorage.getItem("winchicken_tokens");
  return raw ? JSON.parse(raw) : null;
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
      refreshPromise = refreshPromise || client.post("/auth/refresh/", { refresh: tokens.refresh });
      const { data } = await refreshPromise;
      refreshPromise = null;
      setTokens({ ...tokens, access: data.access });
      original.headers.Authorization = `Bearer ${data.access}`;
      return client(original);
    } catch (refreshError) {
      refreshPromise = null;
      setTokens(null);
      window.location.href = "/login";
      return Promise.reject(refreshError);
    }
  }
);

export default client;
