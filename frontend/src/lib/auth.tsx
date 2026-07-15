"use client";

// Client-side auth context. On mount it resolves the current user via
// /api/auth/me (attempting a single refresh on 401). Components read `useAuth`.

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { ApiError, authApi } from "./api";
import type { User } from "./types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  const resolveUser = useCallback(async () => {
    try {
      setUser(await authApi.me());
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        // Try one silent refresh before giving up.
        try {
          const res = await authApi.refresh();
          setUser(res.user);
          return;
        } catch {
          setUser(null);
        }
      } else {
        setUser(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void resolveUser();
  }, [resolveUser]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await authApi.login(email, password);
    // A second step (2FA / email code) can't complete here — the login page
    // handles the challenge flow directly. This context helper is for the
    // simple single-step case.
    if ("user" in res) {
      setUser(res.user);
    } else {
      throw new ApiError(401, "verification_required", "Additional verification required. Please sign in from the login page.");
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setUser(null);
      router.push("/login");
    }
  }, [router]);

  return (
    <AuthContext.Provider
      value={{ user, loading, login, logout, refreshUser: resolveUser }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
