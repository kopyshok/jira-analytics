export const CATEGORY_LABELS: Record<string, string> = {
  support_consultation: 'Сопровождение и консультация',
  business_analysis: 'Анализ/развитие бизнес-процессов',
  meetings: 'Встречи вне развития и консультации',
  admin_losses: 'Административные потери',
  internal_communications: 'Внутренние коммуникации',
  tech_debt: 'Технический долг / прочее',
  unfilled_worklog: 'Незаполненные / сомнительные worklog',
};

export const CATEGORY_COLORS: Record<string, string> = {
  support_consultation: '#378ADD',
  business_analysis: '#1D9E75',
  meetings: '#EF9F27',
  admin_losses: '#E24B4A',
  internal_communications: '#7F77DD',
  tech_debt: '#00c9c8',
  unfilled_worklog: '#888780',
};

interface ChartColorsShape {
  blue: string;
  green: string;
  orange: string;
  red: string;
  purple: string;
  cyan: string;
  cyanSecondary: string;
  yellow: string;
  neutral: string;
}

/** Dark-dashboard chart colors (classic palette) */
const CHART_COLORS_CLASSIC: ChartColorsShape = {
  blue: '#378ADD',
  green: '#1D9E75',
  orange: '#EF9F27',
  red: '#E24B4A',
  purple: '#7F77DD',
  cyan: '#00c9c8',
  cyanSecondary: '#4db8e8',
  yellow: '#f5c842',
  neutral: '#888780',
};

const CHART_COLORS_AURORA_DARK_OVERRIDES: ChartColorsShape = {
  blue: '#38bdf8',
  green: '#34d399',
  orange: '#fb923c',
  red: '#fb7185',
  purple: '#a78bfa',
  cyan: '#22d3ee',
  cyanSecondary: '#67e8f9',
  yellow: '#fbbf24',
  neutral: '#7f90b0',
};

const CHART_COLORS_AURORA_LIGHT_OVERRIDES: ChartColorsShape = {
  blue: '#0ea5e9',
  green: '#059669',
  orange: '#ea580c',
  red: '#dc2626',
  purple: '#7c5cf6',
  cyan: '#0891b2',
  cyanSecondary: '#06b6d4',
  yellow: '#d97706',
  neutral: '#707f9e',
};

/** Runtime-aware chart colors. Mirrors DARK_THEME Proxy strategy. */
export const CHART_COLORS: ChartColorsShape = new Proxy(CHART_COLORS_CLASSIC, {
  get(target, prop: string) {
    if (typeof document === 'undefined') return target[prop as keyof ChartColorsShape];
    const root = document.documentElement;
    if (root.getAttribute('data-theme') !== 'aurora') {
      return target[prop as keyof ChartColorsShape];
    }
    const mode = root.getAttribute('data-mode');
    const pool = mode === 'light' ? CHART_COLORS_AURORA_LIGHT_OVERRIDES : CHART_COLORS_AURORA_DARK_OVERRIDES;
    return pool[prop as keyof ChartColorsShape] ?? target[prop as keyof ChartColorsShape];
  },
});

interface DarkThemeShape {
  pageBg: string;
  sidebarBg: string;
  cardBg: string;
  darkAccent: string;
  border: string;
  darkRows: string;
  cyanPrimary: string;
  cyanSecondary: string;
  yellow: string;
  amber: string;
  amberDim: string;
  danger: string;
  success: string;
  textPrimary: string;
  textSecondary: string;
  textMuted: string;
  textHint: string;
  textDim: string;
}

/** Dark-dashboard theme tokens (classic palette) */
const DARK_THEME_CLASSIC: DarkThemeShape = {
  pageBg: '#0d1c33',
  sidebarBg: '#091527',
  cardBg: '#0f2340',
  darkAccent: '#0a2a44',
  border: '#1e3356',
  darkRows: '#152740',
  cyanPrimary: '#00c9c8',
  cyanSecondary: '#4db8e8',
  yellow: '#f5c842',
  amber: '#f5a524',
  amberDim: '#b87b18',
  danger: '#E24B4A',
  success: '#1D9E75',
  textPrimary: '#e8f0fa',
  textSecondary: '#c5d8ee',
  textMuted: '#8faec8',
  textHint: '#6b8aaa',
  textDim: '#4a6a8a',
};

/** Aurora dark/light overrides — keyed by DARK_THEME shape so Proxy can dispatch. */
const AURORA_DARK_TOKENS: DarkThemeShape = {
  pageBg: '#080b16',
  sidebarBg: '#0d1226',
  cardBg: 'rgba(255,255,255,0.045)',
  darkAccent: 'rgba(255,255,255,0.06)',
  border: 'rgba(255,255,255,0.10)',
  darkRows: 'rgba(255,255,255,0.025)',
  cyanPrimary: '#38bdf8',
  cyanSecondary: '#a78bfa',
  yellow: '#fbbf24',
  amber: '#fbbf24',
  amberDim: '#d97706',
  danger: '#fb7185',
  success: '#34d399',
  textPrimary: '#eaf0fb',
  textSecondary: '#b8c6e0',
  textMuted: '#7f90b0',
  textHint: '#5a6a85',
  textDim: '#5a6a85',
};

const AURORA_LIGHT_TOKENS: DarkThemeShape = {
  pageBg: '#eef2fb',
  sidebarBg: 'rgba(255,255,255,0.55)',
  cardBg: 'rgba(255,255,255,0.55)',
  darkAccent: 'rgba(255,255,255,0.75)',
  border: 'rgba(60,90,160,0.18)',
  darkRows: 'rgba(255,255,255,0.4)',
  cyanPrimary: '#0ea5e9',
  cyanSecondary: '#7c5cf6',
  yellow: '#d97706',
  amber: '#d97706',
  amberDim: '#b45309',
  danger: '#e11d48',
  success: '#059669',
  textPrimary: '#16203a',
  textSecondary: '#3f4d6e',
  textMuted: '#707f9e',
  textHint: '#8b97b3',
  textDim: '#8b97b3',
};

/** Runtime-aware Dark theme tokens.
 *  Reads `<html data-theme="aurora" data-mode="dark|light">` on every access:
 *  - classic: returns DARK_THEME_CLASSIC value
 *  - aurora-dark: returns AURORA_DARK_TOKENS value
 *  - aurora-light: returns AURORA_LIGHT_TOKENS value
 *
 *  This drops in for every existing `DARK_THEME.cardBg` / `DARK_THEME.cyanPrimary`
 *  call without touching consumer code. AppLayout dispatcher remounts the entire
 *  shell on theme change, so JSX-baked snapshots re-read fresh values.
 */
export const DARK_THEME: DarkThemeShape = new Proxy(DARK_THEME_CLASSIC, {
  get(target, prop: string) {
    if (typeof document === 'undefined') return target[prop as keyof DarkThemeShape];
    const root = document.documentElement;
    if (root.getAttribute('data-theme') !== 'aurora') {
      return target[prop as keyof DarkThemeShape];
    }
    const mode = root.getAttribute('data-mode');
    const pool = mode === 'light' ? AURORA_LIGHT_TOKENS : AURORA_DARK_TOKENS;
    return pool[prop as keyof DarkThemeShape] ?? target[prop as keyof DarkThemeShape];
  },
});

export type AppTheme = 'dark' | 'dark-blue' | 'dark-slate' | 'dark-charcoal' | 'aurora-dark' | 'aurora-light';

export interface ThemeTokens {
  pageBg: string;
  sidebarBg: string;
  cardBg: string;
  darkAccent: string;
  border: string;
  darkRows: string;
  primary: string;
  primarySecondary: string;
  textPrimary: string;
  textSecondary: string;
  textMuted: string;
  textHint: string;
}

export const APP_THEMES: Record<AppTheme, { label: string; tokens: ThemeTokens }> = {
  'dark': {
    label: 'Тёмный',
    tokens: {
      pageBg: '#141414',
      sidebarBg: '#0a0a0a',
      cardBg: '#1f1f1f',
      darkAccent: '#262626',
      border: '#303030',
      darkRows: '#242424',
      primary: '#177ddc',
      primarySecondary: '#4096ff',
      textPrimary: '#e8e8e8',
      textSecondary: '#bfbfbf',
      textMuted: '#8c8c8c',
      textHint: '#595959',
    },
  },
  'dark-blue': {
    label: 'Тёмно-синий',
    tokens: {
      pageBg: '#0d1c33',
      sidebarBg: '#091527',
      cardBg: '#0f2340',
      darkAccent: '#0a2a44',
      border: '#1e3356',
      darkRows: '#152740',
      primary: '#00c9c8',
      primarySecondary: '#4db8e8',
      textPrimary: '#e8f0fa',
      textSecondary: '#c5d8ee',
      textMuted: '#8faec8',
      textHint: '#6b8aaa',
    },
  },
  'dark-slate': {
    label: 'Серо-синий',
    tokens: {
      pageBg: '#0f172a',
      sidebarBg: '#0a111f',
      cardBg: '#1e293b',
      darkAccent: '#172034',
      border: '#334155',
      darkRows: '#1a2c42',
      primary: '#3b82f6',
      primarySecondary: '#60a5fa',
      textPrimary: '#e2e8f0',
      textSecondary: '#cbd5e1',
      textMuted: '#94a3b8',
      textHint: '#64748b',
    },
  },
  'dark-charcoal': {
    label: 'Тёплый',
    tokens: {
      pageBg: '#1a1714',
      sidebarBg: '#141210',
      cardBg: '#201d19',
      darkAccent: '#252219',
      border: '#2d2922',
      darkRows: '#1e1b17',
      primary: '#d97706',
      primarySecondary: '#f59e0b',
      textPrimary: '#e8e0d5',
      textSecondary: '#d4c9bb',
      textMuted: '#9d8f80',
      textHint: '#7d6f62',
    },
  },
  'aurora-dark': {
    label: 'Aurora тёмная',
    tokens: {
      pageBg: '#080b16',
      sidebarBg: '#0d1226',
      cardBg: 'rgba(255,255,255,0.045)',
      darkAccent: 'rgba(255,255,255,0.06)',
      border: 'rgba(255,255,255,0.10)',
      darkRows: 'rgba(255,255,255,0.025)',
      primary: '#38bdf8',
      primarySecondary: '#a78bfa',
      textPrimary: '#eaf0fb',
      textSecondary: '#b8c6e0',
      textMuted: '#7f90b0',
      textHint: '#5a6a85',
    },
  },
  'aurora-light': {
    label: 'Aurora светлая',
    tokens: {
      pageBg: '#eef2fb',
      sidebarBg: 'rgba(255,255,255,0.55)',
      cardBg: 'rgba(255,255,255,0.55)',
      darkAccent: 'rgba(255,255,255,0.75)',
      border: 'rgba(255,255,255,0.85)',
      darkRows: 'rgba(255,255,255,0.4)',
      primary: '#0ea5e9',
      primarySecondary: '#7c5cf6',
      textPrimary: '#16203a',
      textSecondary: '#3f4d6e',
      textMuted: '#707f9e',
      textHint: '#8b97b3',
    },
  },
};

/** Typography stack — distinctive, not system-font slop */
export const FONTS = {
  display: "'Fraunces', 'Georgia', serif",
  body: "'Manrope', -apple-system, 'Segoe UI', sans-serif",
  mono: "'JetBrains Mono', ui-monospace, 'SF Mono', 'Consolas', monospace",
} as const;

export const QUARTER_MONTHS: Record<number, number[]> = {
  1: [1, 2, 3],
  2: [4, 5, 6],
  3: [7, 8, 9],
  4: [10, 11, 12],
};

export const MONTH_NAMES: Record<number, string> = {
  1: 'Январь', 2: 'Февраль', 3: 'Март',
  4: 'Апрель', 5: 'Май', 6: 'Июнь',
  7: 'Июль', 8: 'Август', 9: 'Сентябрь',
  10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь',
};

