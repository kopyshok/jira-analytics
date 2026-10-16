import { createContext, useContext, useState, useCallback, useLayoutEffect, type ReactNode } from 'react';
import { APP_THEMES, type AppSkin, type AppTheme } from '../utils/constants';

interface ThemeContextValue {
  theme: AppTheme;
  setTheme: (t: AppTheme) => void;
  isAurora: boolean;
  mode: 'dark' | 'light' | null;
  /** Обложка поверх Aurora light (`data-skin`); null — чистая Aurora. */
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

/** Обложка рисуется поверх Aurora light, поэтому её режим всегда светлый. */
function themeMode(t: AppTheme): 'dark' | 'light' {
  return t === 'aurora-dark' ? 'dark' : 'light';
}

function themeSkin(t: AppTheme): AppSkin | null {
  return APP_THEMES[t].skin ?? null;
}

function readStoredTheme(): AppTheme {
  try {
    const v = localStorage.getItem('app_theme');
    if (isKnownTheme(v)) return v;
    // Все прежние темы (dark-blue, dark, dark-slate, dark-charcoal) сведены
    // к Aurora; допустимые значения — ключи APP_THEMES.
  } catch {
    // localStorage unavailable
  }
  return 'aurora-dark';
}

function applyDomAttrs(t: AppTheme): void {
  const root = document.documentElement;
  root.setAttribute('data-theme', 'aurora');
  root.setAttribute('data-mode', themeMode(t));
  const skin = themeSkin(t);
  if (skin) root.setAttribute('data-skin', skin);
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

  // isAurora остался в контракте контекста ради потребителей (графики, токены),
  // но других тем в продукте больше нет — всегда true.
  const isAurora = true;
  const mode = themeMode(theme);
  const skin = themeSkin(theme);

  return (
    <ThemeContext.Provider value={{ theme, setTheme, isAurora, mode, skin }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useAppTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
