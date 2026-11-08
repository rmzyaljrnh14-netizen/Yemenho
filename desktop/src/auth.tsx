import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getAccess } from "./api";
import type { Me } from "./types";

interface AuthState {
  me: Me | null;
  loading: boolean;
  error: string | null;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      if (!getAccess()) {
        setLoading(false);
        return;
      }
      try {
        setMe(await api.me());
      } catch {
        api.logout();
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function signIn(username: string, password: string) {
    setError(null);
    try {
      await api.login(username, password);
      setMe(await api.me());
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر تسجيل الدخول.");
      throw e;
    }
  }

  function signOut() {
    api.logout();
    setMe(null);
  }

  return (
    <AuthContext.Provider value={{ me, loading, error, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export function hasPermission(me: Me | null, perm: string): boolean {
  return !!me?.scopes.includes(perm);
}
