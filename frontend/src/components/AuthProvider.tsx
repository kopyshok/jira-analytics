import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { getMe, logout as apiLogout, updateMyTeams, type UserProfile } from '../api/auth';
import { AUTH_EXPIRED_EVENT } from '../api/client';
import { AuthContext, type AuthState } from '../hooks/useAuth';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // На монтировании пробуем поднять профиль по cookie. 401 = не залогинен.
  useEffect(() => {
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
        if (!cancelled) setUser(null);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  // 401 от любого endpoint → клиент эмитит auth:expired → сбрасываем профиль.
  useEffect(() => {
    const handler = () => setUser(null);
    window.addEventListener(AUTH_EXPIRED_EVENT, handler);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handler);
  }, []);

  const login = useCallback((profile: UserProfile) => {
    setUser(profile);
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } catch {
      /* even if request fails, drop client state */
    }
    setUser(null);
  }, []);

  const updateUser = useCallback((next: UserProfile) => setUser(next), []);

  const value = useMemo<AuthState>(
    () => ({ user, isLoading, login, logout, updateUser }),
    [user, isLoading, login, logout, updateUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
