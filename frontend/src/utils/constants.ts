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

/** Dark-dashboard chart colors */
export const CHART_COLORS = {
  blue: '#378ADD',
  green: '#1D9E75',
  orange: '#EF9F27',
  red: '#E24B4A',
  purple: '#7F77DD',
  cyan: '#00c9c8',
  cyanSecondary: '#4db8e8',
  yellow: '#f5c842',
  neutral: '#888780',
} as const;

/** Dark-dashboard theme tokens */
export const DARK_THEME = {
  pageBg: '#0d1c33',
  sidebarBg: '#091527',
  cardBg: '#0f2340',
  darkAccent: '#0a2a44',
  border: '#1e3356',
  darkRows: '#152740',
  cyanPrimary: '#00c9c8',
  cyanSecondary: '#4db8e8',
  yellow: '#f5c842',
  /** Warm accent — reserved for critical signals (errors, overrun, stale sync) */
  amber: '#f5a524',
  amberDim: '#b87b18',
  /** Critical / error signal */
  danger: '#E24B4A',
  /** Positive delta (growth, completion) */
  success: '#1D9E75',
  textPrimary: '#e8f0fa',
  textSecondary: '#c5d8ee',
  textMuted: '#8faec8',
  textHint: '#6b8aaa',
  textDim: '#4a6a8a',
} as const;

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

