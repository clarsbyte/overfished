import React, { createContext, useCallback, useContext, useMemo, useState } from "react";

import { DEV_FAKE_AUTH_STORAGE_KEY } from "@/lib/devFakeAuth";

export type DevFakeUser = {
  email: string;
  name: string;
  sub: string;
};

type Ctx = {
  isAuthenticated: boolean;
  user: DevFakeUser | null;
  login: () => void;
  logout: () => void;
};

const DevFakeAuthContext = createContext<Ctx | null>(null);

function readStored(): boolean {
  try {
    return window.localStorage.getItem(DEV_FAKE_AUTH_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function DevFakeAuthProvider({ children }: { children: React.ReactNode }) {
  const [isAuthenticated, setAuthenticated] = useState(() =>
    typeof window !== "undefined" ? readStored() : false,
  );

  const login = useCallback(() => {
    try {
      window.localStorage.setItem(DEV_FAKE_AUTH_STORAGE_KEY, "1");
    } catch {
      /* ignore */
    }
    setAuthenticated(true);
  }, []);

  const logout = useCallback(() => {
    try {
      window.localStorage.removeItem(DEV_FAKE_AUTH_STORAGE_KEY);
    } catch {
      /* ignore */
    }
    setAuthenticated(false);
  }, []);

  const user: DevFakeUser | null = isAuthenticated
    ? {
        email: "dev@localhost",
        name: "Dev user",
        sub: "dev-fake|local",
      }
    : null;

  const value = useMemo(
    () => ({ isAuthenticated, user, login, logout }),
    [isAuthenticated, login, logout],
  );

  return <DevFakeAuthContext.Provider value={value}>{children}</DevFakeAuthContext.Provider>;
}

export function useDevFakeAuth(): Ctx {
  const c = useContext(DevFakeAuthContext);
  if (!c) throw new Error("useDevFakeAuth must be used under DevFakeAuthProvider");
  return c;
}
