import { createContext, useContext, useState, useCallback, useLayoutEffect, type ReactNode } from 'react';
import { APP_THEMES, type AppTheme } from '../utils/constants';

interface ThemeContextValue {
  theme: AppTheme;
  setTheme: (t: AppTheme) => void;
  isAurora: boolean;
  mode: 'dark' | 'light' | null;
  /** Стиль поверх Aurora light (`<html data-skin>`), у самих тем Aurora — null. */
  skin: string | null;
}

export const ThemeContext = createContext<ThemeContextValue>({
  theme: 'aurora-dark',
  setTheme: () => {},
  isAurora: true,
  mode: 'dark',
  skin: null,
});

function isAppTheme(v: string | null): v is AppTheme {
  return v !== null && Object.prototype.hasOwnProperty.call(APP_THEMES, v);
}

function readStoredTheme(): AppTheme {
  try {
    const v = localStorage.getItem('app_theme');
    if (isAppTheme(v)) return v;
    // Все прежние темы (dark-blue, dark, dark-slate, dark-charcoal) сведены
    // к Aurora — неизвестное значение даёт тему по умолчанию.
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
  // Скин — слой поверх Aurora light; у самих тем Aurora атрибута быть не должно.
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

  // isAurora остался в контракте контекста ради потребителей (графики, токены),
  // но других тем в продукте больше нет — всегда true (скины лежат поверх Aurora light).
  const isAurora = true;
  const mode: 'dark' | 'light' = APP_THEMES[theme].mode;
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

/** Активный скин поверх Aurora light (`'warm'` и т.п.) или null у самих тем Aurora.
 *  По нему страница выбирает раскладку скина; данные и обработчики у раскладок общие. */
export function useSkin(): string | null {
  return useContext(ThemeContext).skin;
}
