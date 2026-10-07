import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
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
  // True while CreateFarmPage's account creation is still finishing in the background (it
  // navigates to onboarding before awaiting the request — see createAccountInBackground below).
  // Django's password hash (PBKDF2) is deliberately slow, several seconds on a farm PC's modest,
  // often-virtualized hardware; ProtectedRoute reads this to let the onboarding routes render
  // without a `user` instead of bouncing to /login while it's true.
  const [creatingAccount, setCreatingAccount] = useState(false);
  // The error from a background creation that ultimately failed, read by CreateFarmPage once
  // ProtectedRoute redirects back to it (no user ever showed up and this is set).
  const [accountCreationError, setAccountCreationError] = useState(null);
  const pendingAccountRef = useRef(null);

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

  // CreateFarmPage calls this right after firing POST /api/farm/create/ and navigates
  // immediately, instead of awaiting it: nothing in the onboarding sequence needs the account to
  // exist yet (the first step that does — OnboardingProtocolPage's save — awaits
  // waitForAccount() below before it fires). `requestPromise` is the raw farmApi.create() call;
  // this wires its result into the normal login (same token/profile handling as the old
  // synchronous flow) without the caller having to.
  const createAccountInBackground = useCallback((requestPromise) => {
    setAccountCreationError(null);
    setCreatingAccount(true);
    const settled = requestPromise
      .then(({ data }) => loginWithTokens(data))
      .catch((err) => {
        setAccountCreationError(err);
        throw err;
      })
      .finally(() => setCreatingAccount(false));
    pendingAccountRef.current = settled;
    return settled;
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- loginWithTokens is stable (closes over setState only)

  // Resolves once a background account creation has settled — immediately if none is pending.
  // Never rejects: a failure is read from accountCreationError, not this promise, since by the
  // time most callers await it they only care that it's *done*, not what happened.
  const waitForAccount = useCallback(() => (pendingAccountRef.current || Promise.resolve()).catch(() => {}), []);

  return (
    <AuthContext.Provider value={{
      user, loading, unreachable, loginWithTokens, logout, refreshMe,
      creatingAccount, accountCreationError, setAccountCreationError,
      createAccountInBackground, waitForAccount,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
