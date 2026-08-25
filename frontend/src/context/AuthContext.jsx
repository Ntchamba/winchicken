import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { getTokens, setTokens } from "../api/client";
import { authApi } from "../api/endpoints";

const AuthContext = createContext(null);

// user: { id, name, email, phone, role, farm_name, is_configured } | null while loading
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refreshMe = useCallback(async () => {
    if (!getTokens()) {
      setUser(null);
      setLoading(false);
      return null;
    }
    try {
      const { data } = await authApi.me();
      setUser(data);
      return data;
    } catch {
      setTokens(null);
      setUser(null);
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
  };

  return (
    <AuthContext.Provider value={{ user, loading, loginWithTokens, logout, refreshMe }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
