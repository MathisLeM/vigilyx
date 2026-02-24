"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { login as apiLogin, signup as apiSignup, fetchMe, apiLogout, UserInfo } from "./api";

interface AuthState {
  tenantId: number | null;
  email: string | null;
  isAdmin: boolean;
  loaded: boolean; // true once the initial /auth/me check has completed
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refetchUser: () => Promise<void>;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [auth, setAuth] = useState<AuthState>({
    tenantId: null,
    email: null,
    isAdmin: false,
    loaded: false,
  });

  function applyUser(data: UserInfo) {
    setAuth({
      tenantId: data.tenant_id,
      email: data.email,
      isAdmin: data.is_admin,
      loaded: true,
    });
  }

  // On mount: check the httpOnly cookie via /auth/me
  useEffect(() => {
    fetchMe()
      .then(applyUser)
      .catch(() => setAuth({ tenantId: null, email: null, isAdmin: false, loaded: true }));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const data = await apiLogin(email, password);
    applyUser(data);
  }, []);

  const signup = useCallback(async (email: string, password: string) => {
    const data = await apiSignup(email, password);
    applyUser(data);
  }, []);

  const logout = useCallback(async () => {
    await apiLogout();
    setAuth({ tenantId: null, email: null, isAdmin: false, loaded: true });
  }, []);

  // Call this after any flow that sets the cookie outside the normal login/signup
  // (e.g. invitation accept), then redirect.
  const refetchUser = useCallback(async () => {
    try {
      const data = await fetchMe();
      applyUser(data);
    } catch {
      setAuth({ tenantId: null, email: null, isAdmin: false, loaded: true });
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{
        ...auth,
        login,
        signup,
        logout,
        refetchUser,
        isAuthenticated: auth.loaded && !!auth.email,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
