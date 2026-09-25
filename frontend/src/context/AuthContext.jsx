import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { USER_CACHE_KEY, getTokens, setTokens } from "../api/client";
import { authApi } from "../api/endpoints";

const AuthContext = createContext(null);

// The last known profile, read only when there are tokens to go with it. Opening the app on a
// slow farm connection used to show a bare "Chargement…" — no navigation, nothing to do — for as
// long as /auth/me took; with the profile at hand the dashboard opens at once and /auth/me
// refreshes it in the background (2026-09-25).
function cachedUser() {
  try {
    if (!getTokens()) return null;
    const raw = localStorage.getItem(USER_CACHE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function cacheUser(user) {
  try {
    if (user) localStorage.setItem(USER_CACHE_KEY, JSON.stringify(user));
    else localStorage.removeItem(USER_CACHE_KEY);
  } catch {
    // Storage refused (private mode): the app still works, it just waits for /auth/me.
  }
}

// user: { id, name, email, phone, role, farm_name, is_configured } | null while loading
export function AuthProvider({ children }) {
  const [user, setUser] = useState(cachedUser);
  const [loading, setLoading] = useState(() => !cachedUser() && !!getTokens());
  // Set when /auth/me could not be reached at all (no answer, or a server error) and there is
  // no cached profile to open with: ProtectedRoute shows a retry screen instead of a login form.
  const [unreachable, setUnreachable] = useState(false);

  const refreshMe = useCallback(async () => {
    if (!getTokens()) {
      setUser(null);
      setLoading(false);
      return null;
    }
    try {
      const { data } = await authApi.me();
      setUser(data);
      cacheUser(data);
      setUnreachable(false);
      return data;
    } catch (err) {
      // Only the server saying "not you" ends the session. A dropped connection or a server
      // error used to log the worker out too — on a flaky farm network, at every app start.
      if (err?.response?.status === 401 || err?.response?.status === 403) {
        setTokens(null);
        setUser(null);
        return null;
      }
      setUnreachable(true);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshMe();
  }, [refreshMe]);

  const loginWithTokens = async (tokenResponse) => {
    setTokens({ access: tokenResponse.access, refresh: tokenResponse.refresh });
    return refreshMe();
  };

  const logout = () => {
    setTokens(null);
    setUser(null);
    setUnreachable(false);
  };

  return (
    <AuthContext.Provider value={{ user, loading, unreachable, loginWithTokens, logout, refreshMe }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
