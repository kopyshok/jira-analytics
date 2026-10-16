import { useMemo } from 'react';
import { useAppTheme } from '../../contexts/ThemeContext';
import { DARK_THEME } from '../../utils/constants';

/**
 * Runtime token map that mirrors the DARK_THEME shape but swaps values to
 * Aurora glass tokens when isAurora=true. Drop-in replacement for code that
 * imports DARK_THEME directly — call `const t = useThemeTokens()` and use
 * `t.pageBg` / `t.cardBg` / ... instead.
 *
 * Aurora values come from glass.css via CSS variables (var(--...)) so they
 * stay in sync with theme switches without a re-render.
 */
export function useThemeTokens() {
  const { isAurora, mode, skin } = useAppTheme();
  return useMemo(() => {
    if (!isAurora) return DARK_THEME;

    const isDark = mode === 'dark';
    // «Пульт»: тёплые сплошные тона вместо голубых полупрозрачных подложек Aurora light.
    const isPult = skin === 'pult';
    return {
      pageBg: 'var(--bg)',
      sidebarBg: isPult ? '#F4F3EF' : isDark ? 'rgba(13,18,38,0.6)' : 'rgba(255,255,255,0.55)',
      cardBg: 'var(--glass-bg)',
      darkAccent: isPult ? '#EFEDE7' : isDark ? 'rgba(255,255,255,0.06)' : 'rgba(60,90,160,0.06)',
      border: 'var(--glass-border)',
      darkRows: isPult ? '#EFEDE7' : isDark ? 'rgba(255,255,255,0.025)' : 'rgba(60,90,160,0.04)',
      cyanPrimary: 'var(--accent-1)',
      cyanSecondary: 'var(--accent-2)',
      yellow: 'var(--warn)',
      amber: 'var(--warn)',
      amberDim: isPult ? '#6E4D00' : isDark ? '#fbbf24cc' : '#d97706cc',
      danger: 'var(--bad)',
      success: 'var(--good)',
      textPrimary: 'var(--text)',
      textSecondary: 'var(--text-2)',
      textMuted: 'var(--text-muted)',
      textHint: 'var(--text-muted)',
      textDim: isPult ? '#6E6B64' : isDark ? '#5a6a85' : '#8b97b3',
    };
  }, [isAurora, mode, skin]);
}
