import { useCallback, useEffect } from 'react';
import { useAppTheme } from '../contexts/ThemeContext';
import { useAuth } from './useAuth';
import { api } from '../api/client';
import type { AppTheme } from '../utils/constants';

export function useThemeSync() {
  const { user } = useAuth();
  const { setTheme } = useAppTheme();

  // On login, sync server theme to local context
  useEffect(() => {
    if (user?.selected_theme) {
      const t = user.selected_theme as AppTheme;
      setTheme(t);
    }
  }, [user?.selected_theme, setTheme]);
}

export function useSaveTheme() {
  const { setTheme } = useAppTheme();

  return useCallback(async (t: AppTheme) => {
    setTheme(t); // immediate local update
    await api.put('/users/me/theme', { theme: t });
  }, [setTheme]);
}
