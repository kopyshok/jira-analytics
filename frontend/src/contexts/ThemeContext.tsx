import { createContext, useContext, useState, useCallback, useLayoutEffect, type ReactNode } from 'react';
import { APP_THEMES, type AppSkin, type AppTheme } from '../utils/constants';

interface ThemeContextValue {
  theme: AppTheme;
  setTheme: (t: AppTheme) => void;
  isAurora: boolean;
  mode: 'dark' | 'light' | null;
  /** Скин поверх Aurora light (`<html data-skin>`), null — чистая Aurora. */
  skin: AppSkin | null;
}

export const ThemeContext = createContext<ThemeContextValue>({
  theme: 'aurora-dark',
  setTheme: () => {},
  isAurora: true,
  mode: 'dark',
  skin: null,
});

function isKnownTheme(v: string | null): v is AppTheme {
  return v !== null && Object.prototype.hasOwnProperty.call(APP_THEMES, v);
}

function readStoredTheme(): AppTheme {
  try {
    const v = localStorage.getItem('app_theme');
    if (isKnownTheme(v)) return v;
    // Все прежние темы (dark-blue, dark, dark-slate, dark-charcoal) сведены
    // к Aurora по умолчанию.
  } catch {
    // localStorage unavailable
  }
  return 'aurora-dark';
}

function applyDomAttrs(t: AppTheme): void {
  const root = document.documentElement;
  const def = APP_THEMES[t];
  root.setAttribute('data-theme', 'aurora');
  root.setAttribute('data-mode', def.mode);
  // Скин ложится слоем поверх Aurora light; у самих тем Aurora атрибута нет.
  if (def.skin) root.setAttribute('data-skin', def.skin);
  else root.removeAttribute('data-skin');
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

  // isAurora остался в контракте контекста ради потребителей (графики, токены):
  // все темы продукта — Aurora (скины ложатся поверх Aurora light), всегда true.
  const isAurora = true;
  const { mode } = APP_THEMES[theme];
  const skin = APP_THEMES[theme].skin ?? null;

  return (
    <ThemeContext.Provider value={{ theme, setTheme, isAurora, mode, skin }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useAppTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
