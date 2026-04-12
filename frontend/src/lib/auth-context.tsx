"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import { api } from "./api";

interface User {
  id: string;
  email: string;
  display_name: string | null;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<any>;
  verify2FA: (token2FA: string, code: string) => Promise<void>;
  verifyRecoveryCode: (token2FA: string, code: string) => Promise<void>;
  register: (
    email: string,
    password: string,
    displayName?: string,
    inviteToken?: string
  ) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  const refreshUser = useCallback(async () => {
    try {
      const me = await api.getMe();
      setUser(me);
    } catch (err: any) {
      setUser(null);
      if (err.message === "Not authenticated") {
        api.clearTokens();
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = async (email: string, password: string) => {
    const res = await api.login(email, password);
    if (res.requires_2fa) {
      return res; // Return the 2FA token to the login page
    }
    await refreshUser();
    router.push("/");
    return res;
  };

  const verify2FA = async (token2FA: string, code: string) => {
    await api.verify2FA(token2FA, code);
    await refreshUser();
    router.push("/");
  };

  const verifyRecoveryCode = async (token2FA: string, code: string) => {
    await api.verifyRecoveryCode(token2FA, code);
    await refreshUser();
    router.push("/");
  };

  const register = async (
    email: string,
    password: string,
    displayName?: string,
    inviteToken?: string
  ) => {
    await api.register(email, password, displayName, inviteToken);
    await api.login(email, password);
    await refreshUser();
    router.push("/");
  };

  const logout = () => {
    api.logout();
    setUser(null);
    router.push("/login");
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        verify2FA,
        verifyRecoveryCode,
        register,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
