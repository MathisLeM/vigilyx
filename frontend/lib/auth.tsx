"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { login as apiLogin, signup as apiSignup, LoginResponse } from "./api";

interface AuthState {
  token: string | null;
  tenantId: number | null;
  email: string | null;
  isAdmin: boolean;
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [auth, setAuth] = useState<AuthState>({
    token: null,
    tenantId: null,
    email: null,
    isAdmin: false,
  });

  // Rehydrate from localStorage on mount
  useEffect(() => {
    const token = localStorage.getItem("token");
    const tenantId = localStorage.getItem("tenantId");
    const email = localStorage.getItem("email");
    const isAdmin = localStorage.getItem("isAdmin") === "true";
    if (token) {
      setAuth({
        token,
        tenantId: tenantId ? Number(tenantId) : null,
        email,
        isAdmin,
      });
    }
  }, []);

  function storeAuth(data: LoginResponse) {
    localStorage.setItem("token", data.access_token);
    localStorage.setItem("tenantId", data.tenant_id != null ? String(data.tenant_id) : "");
    localStorage.setItem("email", data.email);
    localStorage.setItem("isAdmin", String(data.is_admin));
    setAuth({
      token: data.access_token,
      tenantId: data.tenant_id,
      email: data.email,
      isAdmin: data.is_admin,
    });
  }

  const login = useCallback(async (email: string, password: string) => {
    const data: LoginResponse = await apiLogin(email, password);
    storeAuth(data);
  }, []);

  const signup = useCallback(async (email: string, password: string) => {
    const data: LoginResponse = await apiSignup(email, password);
    storeAuth(data);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("token");
    localStorage.removeItem("tenantId");
    localStorage.removeItem("email");
    localStorage.removeItem("isAdmin");
    setAuth({ token: null, tenantId: null, email: null, isAdmin: false });
  }, []);

  return (
    <AuthContext.Provider
      value={{ ...auth, login, signup, logout, isAuthenticated: !!auth.token }}
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
