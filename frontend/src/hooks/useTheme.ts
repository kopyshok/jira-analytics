import { useCallback, useEffect, useRef } from 'react';
import { useAppTheme } from '../contexts/ThemeContext';
import { useAuth } from './useAuth';
import { api } from '../api/client';
import { APP_THEMES, type AppTheme } from '../utils/constants';

function normalizeTheme(v: string | null | undefined): AppTheme {
  if (v && (v in APP_THEMES)) return v as AppTheme;
  // Legacy / removed темы (dark, dark-slate, dark-charcoal) → aurora-dark
  return 'aurora-dark';
}

export function useThemeSync() {
  const { user } = useAuth();
  const { setTheme } = useAppTheme();
  const lastSyncedUserId = useRef<string | null>(null);

  // Apply server theme exactly once per login. After that, only explicit
  // saveTheme() calls update the local context — otherwise this hook would
  // overwrite user toggles every time the shell remounts (e.g. when switching
  // between AuroraShell and ClassicShell).
  useEffect(() => {
    if (user?.id && user.id !== lastSyncedUserId.current) {
      lastSyncedUserId.current = user.id;
      if (user.selected_theme) {
        setTheme(normalizeTheme(user.selected_theme));
      }
    } else if (!user) {
      lastSyncedUserId.current = null;
    }
  }, [user, setTheme]);
}

export function useSaveTheme() {
  const { setTheme } = useAppTheme();
  const { user, updateUser } = useAuth();

  return useCallback(async (t: AppTheme) => {
    setTheme(t); // immediate local update — visual change applies even if API fails
    // Keep the cached user profile in sync so useThemeSync (which fires on the
    // initial login) doesn't overwrite the new choice if the shell remounts.
    if (user) updateUser({ ...user, selected_theme: t });
    try {
      await api.put('/users/me/theme', { theme: t });
    } catch (err) {
      // Backend can reject (e.g. legacy backend without aurora-* in VALID_THEMES)
      // Local theme still applies for this session; will retry on next save.
      console.warn('Theme persist failed; using local-only theme.', err);
    }
  }, [setTheme, user, updateUser]);
}
