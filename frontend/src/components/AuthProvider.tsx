import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { getMe, updateMyTeams, type UserProfile } from '../api/auth';
import { AuthContext, type AuthState } from '../hooks/useAuth';

const TOKEN_KEY = 'auth_token';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!token) {
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    getMe()
      .then(async (me) => {
        if (cancelled) return;
        if (me.selected_teams.length === 0 && me.default_team) {
          try {
            const seeded = await updateMyTeams([me.default_team]);
            if (!cancelled) setUser(seeded);
          } catch {
            if (!cancelled) setUser(me);
          }
        } else {
          setUser(me);
        }
      })
      .catch(() => {
        if (cancelled) return;
        localStorage.removeItem(TOKEN_KEY);
        setToken(null);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => { cancelled = true; };
  }, [token]);

  const login = useCallback((newToken: string, profile: UserProfile) => {
    localStorage.setItem(TOKEN_KEY, newToken);
    setToken(newToken);
    setUser(profile);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  }, []);

  const updateUser = useCallback((next: UserProfile) => setUser(next), []);

  const value = useMemo<AuthState>(
    () => ({ user, token, isLoading, login, logout, updateUser }),
    [user, token, isLoading, login, logout, updateUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
