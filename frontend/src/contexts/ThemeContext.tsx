import { createContext, useContext, useState, useCallback, useLayoutEffect, type ReactNode } from 'react';
import type { AppTheme } from '../utils/constants';

interface ThemeContextValue {
  theme: AppTheme;
  setTheme: (t: AppTheme) => void;
  isAurora: boolean;
  mode: 'dark' | 'light' | null;
}

export const ThemeContext = createContext<ThemeContextValue>({
  theme: 'aurora-dark',
  setTheme: () => {},
  isAurora: true,
  mode: 'dark',
});

function readStoredTheme(): AppTheme {
  try {
    const v = localStorage.getItem('app_theme');
    if (
      v === 'dark' || v === 'dark-blue' || v === 'dark-slate' || v === 'dark-charcoal' ||
      v === 'aurora-dark' || v === 'aurora-light'
    ) return v;
  } catch {
    // localStorage unavailable
  }
  return 'aurora-dark';
}

function applyDomAttrs(t: AppTheme): void {
  const root = document.documentElement;
  if (t === 'aurora-dark') {
    root.setAttribute('data-theme', 'aurora');
    root.setAttribute('data-mode', 'dark');
  } else if (t === 'aurora-light') {
    root.setAttribute('data-theme', 'aurora');
    root.setAttribute('data-mode', 'light');
  } else {
    root.setAttribute('data-theme', 'classic');
    root.removeAttribute('data-mode');
  }
}

// Apply DOM attrs eagerly on module load — before any React render reads the Proxy.
// Otherwise inline `style={{ color: DARK_THEME.textPrimary }}` snapshots the wrong
// branch (Proxy sees no data-mode attr yet) and stays in classic colors until next
// rerender, producing white-on-white in Aurora-light.
if (typeof document !== 'undefined') {
  applyDomAttrs(readStoredTheme());
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<AppTheme>(readStoredTheme);

  // useLayoutEffect (sync) instead of useEffect (async) — flush DOM attrs
  // before browser paints; pairs with the eager module-load apply above.
  useLayoutEffect(() => { applyDomAttrs(theme); }, [theme]);

  const setTheme = useCallback((t: AppTheme) => {
    try { localStorage.setItem('app_theme', t); } catch { /* ignore */ }
    applyDomAttrs(t);
    setThemeState(t);
  }, []);

  const isAurora = theme === 'aurora-dark' || theme === 'aurora-light';
  const mode: 'dark' | 'light' | null = theme === 'aurora-dark' ? 'dark' : theme === 'aurora-light' ? 'light' : null;

  return (
    <ThemeContext.Provider value={{ theme, setTheme, isAurora, mode }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useAppTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
