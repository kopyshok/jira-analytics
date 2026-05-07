import { createContext, useContext, useState, useCallback, type ReactNode } from 'react';
import type { AppTheme } from '../utils/constants';

interface ThemeContextValue {
  theme: AppTheme;
  setTheme: (t: AppTheme) => void;
}

export const ThemeContext = createContext<ThemeContextValue>({
  theme: 'dark-blue',
  setTheme: () => {},
});

function readStoredTheme(): AppTheme {
  try {
    const v = localStorage.getItem('app_theme');
    if (v === 'dark-blue' || v === 'dark-slate' || v === 'dark-charcoal') return v;
  } catch {
    // localStorage unavailable
  }
  return 'dark-blue';
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<AppTheme>(readStoredTheme);

  const setTheme = useCallback((t: AppTheme) => {
    try {
      localStorage.setItem('app_theme', t);
    } catch {
      // ignore
    }
    setThemeState(t);
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useAppTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
