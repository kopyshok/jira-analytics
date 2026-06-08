import { useMemo } from 'react';
import { useAppTheme } from '../../contexts/ThemeContext';
import { CHART_COLORS, DARK_THEME } from '../../utils/constants';
import { CHART_COLORS_AURORA, CHART_PALETTE_AURORA } from './colors';

export function useChartTheme() {
  const { isAurora, mode } = useAppTheme();
  return useMemo(() => {
    if (!isAurora) {
      return {
        isAurora: false as const,
        mode: null as null,
        palette: Object.values(CHART_COLORS) as string[],
        colors: CHART_COLORS,
        gridStroke: DARK_THEME.border,
        axisColor: DARK_THEME.textMuted,
        tooltipBg: DARK_THEME.cardBg,
      };
    }
    const isDark = mode === 'dark';
    return {
      isAurora: true as const,
      mode,
      palette: CHART_PALETTE_AURORA,
      colors: CHART_COLORS_AURORA,
      gridStroke: isDark ? 'rgba(255,255,255,0.10)' : 'rgba(60,90,160,0.12)',
      axisColor: isDark ? '#7f90b0' : '#707f9e',
      tooltipBg: isDark ? 'rgba(20,25,40,0.95)' : 'rgba(255,255,255,0.95)',
    };
  }, [isAurora, mode]);
}
