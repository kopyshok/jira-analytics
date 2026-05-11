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

export type AppTheme = 'dark' | 'dark-blue' | 'dark-slate' | 'dark-charcoal';

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
};

// ============================================================================
// Theme Tokens V2 — semantic groups, реактивные через useThemeTokens()
// ============================================================================
//
// Параллельная архитектура к APP_THEMES + DARK_THEME (legacy flat tokens).
// Новый и мигрируемый код использует THEME_TOKENS_V2 через хук useThemeTokens.
// Старая структура (APP_THEMES, DARK_THEME) сохраняется для существующих
// потребителей — миграция файл за файлом, без массового rewrite.
//
// После завершения миграции (Stage 3-4 в spec) — legacy уберётся, V2 станет
// единственной (возможно, переименуется обратно в APP_THEMES).

export type ChartRoleKey = 'blue' | 'green' | 'orange' | 'purple' | 'cyan' | 'red' | 'neutral' | 'yellow';

export interface ThemeTokensV2 {
  surface: {
    /** Основной фон страницы */
    page: string;
    /** Боковая панель, header */
    sidebar: string;
    /** Карточки, модалки, popover, drawer */
    card: string;
    /** Активная подсветка, hover-state, выделенная строка */
    accent: string;
    /** Чередующиеся строки таблиц */
    rows: string;
  };
  text: {
    /** Заголовки, основной контент */
    primary: string;
    /** Body-текст, описания */
    secondary: string;
    /** Лейблы, метаданные, второстепенная информация */
    muted: string;
    /** Eyebrow, caption, мелкий вспомогательный */
    hint: string;
    /** Disabled, placeholder */
    dim: string;
  };
  border: {
    /** Тонкие разделители внутри карточек */
    subtle: string;
    /** Рамки карточек, дефолтные границы */
    default: string;
  };
  accent: {
    /** CTA, ссылки, ключевые акценты */
    primary: string;
    /** Hover-состояние, вторичные кнопки */
    secondary: string;
  };
  status: {
    /** Позитивный сигнал (рост, выполнено) */
    success: string;
    /** Внимание (просрочка, перегрузка) */
    warning: string;
    /** Критично (ошибка, блокер) */
    danger: string;
    /** Нейтральная информация */
    info: string;
  };
  chart: {
    /** Упорядоченный список серийных цветов для легенды */
    series: string[];
    /** Именованный доступ к тем же цветам */
    byRole: Record<ChartRoleKey, string>;
  };
}

const CHART_PALETTE_SERIES = [
  '#378ADD',
  '#1D9E75',
  '#EF9F27',
  '#7F77DD',
  '#00c9c8',
  '#E24B4A',
  '#888780',
  '#f5c842',
] as const;

const CHART_PALETTE_BY_ROLE: Record<ChartRoleKey, string> = {
  blue: '#378ADD',
  green: '#1D9E75',
  orange: '#EF9F27',
  purple: '#7F77DD',
  cyan: '#00c9c8',
  red: '#E24B4A',
  neutral: '#888780',
  yellow: '#f5c842',
};

export const THEME_TOKENS_V2: Record<AppTheme, ThemeTokensV2> = {
  'dark': {
    surface: {
      page: '#141414',
      sidebar: '#0a0a0a',
      card: '#1f1f1f',
      accent: '#262626',
      rows: '#242424',
    },
    text: {
      primary: '#e8e8e8',
      secondary: '#bfbfbf',
      muted: '#8c8c8c',
      hint: '#595959',
      dim: '#404040',
    },
    border: {
      subtle: 'rgba(255,255,255,0.06)',
      default: '#303030',
    },
    accent: {
      primary: '#177ddc',
      secondary: '#4096ff',
    },
    status: {
      success: '#1D9E75',
      warning: '#f5a524',
      danger: '#E24B4A',
      info: '#4db8e8',
    },
    chart: {
      series: [...CHART_PALETTE_SERIES],
      byRole: { ...CHART_PALETTE_BY_ROLE },
    },
  },
  'dark-blue': {
    surface: {
      page: '#0d1c33',
      sidebar: '#091527',
      card: '#0f2340',
      accent: '#0a2a44',
      rows: '#152740',
    },
    text: {
      primary: '#e8f0fa',
      secondary: '#c5d8ee',
      muted: '#8faec8',
      hint: '#6b8aaa',
      dim: '#4a6a8a',
    },
    border: {
      subtle: 'rgba(255,255,255,0.06)',
      default: '#1e3356',
    },
    accent: {
      primary: '#00c9c8',
      secondary: '#4db8e8',
    },
    status: {
      success: '#1D9E75',
      warning: '#f5a524',
      danger: '#E24B4A',
      info: '#4db8e8',
    },
    chart: {
      series: [...CHART_PALETTE_SERIES],
      byRole: { ...CHART_PALETTE_BY_ROLE },
    },
  },
  'dark-slate': {
    surface: {
      page: '#0f172a',
      sidebar: '#0a111f',
      card: '#1e293b',
      accent: '#172034',
      rows: '#1a2c42',
    },
    text: {
      primary: '#e2e8f0',
      secondary: '#cbd5e1',
      muted: '#94a3b8',
      hint: '#64748b',
      dim: '#475569',
    },
    border: {
      subtle: 'rgba(255,255,255,0.05)',
      default: '#334155',
    },
    accent: {
      primary: '#3b82f6',
      secondary: '#60a5fa',
    },
    status: {
      success: '#22c55e',
      warning: '#f59e0b',
      danger: '#ef4444',
      info: '#60a5fa',
    },
    chart: {
      series: [...CHART_PALETTE_SERIES],
      byRole: { ...CHART_PALETTE_BY_ROLE },
    },
  },
  'dark-charcoal': {
    surface: {
      page: '#1a1714',
      sidebar: '#141210',
      card: '#201d19',
      accent: '#252219',
      rows: '#1e1b17',
    },
    text: {
      primary: '#e8e0d5',
      secondary: '#d4c9bb',
      muted: '#9d8f80',
      hint: '#7d6f62',
      dim: '#5d5246',
    },
    border: {
      subtle: 'rgba(255,255,255,0.06)',
      default: '#2d2922',
    },
    accent: {
      primary: '#d97706',
      secondary: '#f59e0b',
    },
    status: {
      success: '#65a30d',
      warning: '#f59e0b',
      danger: '#dc2626',
      info: '#0891b2',
    },
    chart: {
      series: [...CHART_PALETTE_SERIES],
      byRole: { ...CHART_PALETTE_BY_ROLE },
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

