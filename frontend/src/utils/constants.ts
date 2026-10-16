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
  blue: '#3b6ef5',
  green: '#1f9e6f',
  orange: '#d98a2b',
  red: '#e05647',
  purple: '#6d6eef',
  cyan: '#2f8de8',
  cyanSecondary: '#5fa3ec',
  yellow: '#d98a2b',
  neutral: '#8089a0',
};

/* «Пульт» — цвета индикаторов из стиля: синий/янтарь/зелёный/фиолет/красный + сигнальный оранжевый. */
const CHART_COLORS_PULT: ChartColorsShape = {
  blue: '#2F6FDE',
  green: '#2E9E5B',
  orange: '#E8590C',
  red: '#D9381E',
  purple: '#8E5BC2',
  cyan: '#3E8A9E',
  cyanSecondary: '#6FA7B8',
  yellow: '#D99A00',
  neutral: '#9A978F',
};

/** Обложка поверх Aurora light: `<html data-skin="…">`; у самих Aurora атрибута нет. */
function currentSkin(): string | null {
  if (typeof document === 'undefined') return null;
  return document.documentElement.getAttribute('data-skin');
}

/** Runtime-aware chart colors. Mirrors DARK_THEME Proxy strategy. */
export const CHART_COLORS: ChartColorsShape = new Proxy(CHART_COLORS_CLASSIC, {
  get(target, prop: string) {
    if (typeof document === 'undefined') return target[prop as keyof ChartColorsShape];
    const root = document.documentElement;
    if (root.getAttribute('data-theme') !== 'aurora') {
      return target[prop as keyof ChartColorsShape];
    }
    if (currentSkin() === 'pult') return CHART_COLORS_PULT[prop as keyof ChartColorsShape] ?? target[prop as keyof ChartColorsShape];
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

/* Aurora light — «Фарфор» (porcelain neumorphism).
 * Solid surfaces (rgba не работает на inline-style без backdrop-blur).
 * cardBg = page bg = #e6ebf2: глубина задаётся neu-тенями в CSS, не разностью цвета. */
const AURORA_LIGHT_TOKENS: DarkThemeShape = {
  pageBg: '#e6ebf2',
  sidebarBg: '#e6ebf2',
  cardBg: '#e6ebf2',
  darkAccent: '#eef2f7',
  border: 'rgba(195,203,217,0.7)',
  darkRows: '#eef2f7',
  cyanPrimary: '#3b6ef5',
  cyanSecondary: '#2f8de8',
  yellow: '#d98a2b',
  amber: '#d98a2b',
  amberDim: '#b35e0c',
  danger: '#e05647',
  success: '#1f9e6f',
  textPrimary: '#2a3142',
  textSecondary: '#3f4860',
  textMuted: '#5d6680',
  textHint: '#7a8298',
  textDim: '#7a8298',
};

/* «Пульт» (обложка поверх Aurora light) — корпус #E7E5E0, модули #F4F3EF, плоско.
 * Только сплошные цвета. Цвета текста — с контрастом ≥ 4.5:1 на корпусе и модуле. */
const PULT_TOKENS: DarkThemeShape = {
  pageBg: '#E7E5E0',
  sidebarBg: '#F4F3EF',
  cardBg: '#F4F3EF',
  darkAccent: '#EFEDE7',
  border: '#CFCCC4',
  darkRows: '#EFEDE7',
  cyanPrimary: '#A93F0A',
  cyanSecondary: '#2A62C9',
  yellow: '#8F6400',
  amber: '#8F6400',
  amberDim: '#6E4D00',
  danger: '#B92E17',
  success: '#237A45',
  textPrimary: '#1C1C1A',
  textSecondary: '#3D3B37',
  textMuted: '#5C5A55',
  textHint: '#6E6B64',
  textDim: '#6E6B64',
};

/** Runtime-aware Dark theme tokens.
 *  Reads `<html data-theme="aurora" data-mode="dark|light">` on every access:
 *  - classic: returns DARK_THEME_CLASSIC value
 *  - aurora-dark: returns AURORA_DARK_TOKENS value
 *  - aurora-light: returns AURORA_LIGHT_TOKENS value
 *  - pult-light (data-skin="pult"): returns PULT_TOKENS value
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
    if (currentSkin() === 'pult') return PULT_TOKENS[prop as keyof DarkThemeShape] ?? target[prop as keyof DarkThemeShape];
    const mode = root.getAttribute('data-mode');
    const pool = mode === 'light' ? AURORA_LIGHT_TOKENS : AURORA_DARK_TOKENS;
    return pool[prop as keyof DarkThemeShape] ?? target[prop as keyof DarkThemeShape];
  },
});

export type AppTheme = 'aurora-dark' | 'aurora-light' | 'pult-light';

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

/** Обложка (skin) — набор стилей поверх Aurora light; у тем Aurora её нет. */
export type AppSkin = 'pult';

export const APP_THEMES: Record<AppTheme, { label: string; tokens: ThemeTokens; skin?: AppSkin }> = {
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
      pageBg: '#e6ebf2',
      sidebarBg: '#e6ebf2',
      cardBg: '#e6ebf2',
      darkAccent: '#eef2f7',
      border: 'rgba(195,203,217,0.7)',
      darkRows: '#eef2f7',
      primary: '#3b6ef5',
      primarySecondary: '#2f8de8',
      textPrimary: '#2a3142',
      textSecondary: '#3f4860',
      textMuted: '#5d6680',
      textHint: '#7a8298',
    },
  },
  'pult-light': {
    label: 'Пульт',
    skin: 'pult',
    tokens: {
      pageBg: '#E7E5E0',
      sidebarBg: '#F4F3EF',
      cardBg: '#F4F3EF',
      darkAccent: '#EFEDE7',
      border: '#CFCCC4',
      darkRows: '#EFEDE7',
      primary: '#E8590C',
      primarySecondary: '#2A62C9',
      textPrimary: '#1C1C1A',
      textSecondary: '#3D3B37',
      textMuted: '#5C5A55',
      textHint: '#6E6B64',
    },
  },
};

const FONTS_BASE = {
  display: "'Fraunces', 'Georgia', serif",
  body: "'Manrope', -apple-system, 'Segoe UI', sans-serif",
  mono: "'JetBrains Mono', ui-monospace, 'SF Mono', 'Consolas', monospace",
} as const;

const FONTS_PULT: Record<keyof typeof FONTS_BASE, string> = {
  display: "'Commissioner', 'Segoe UI', sans-serif",
  body: "'Commissioner', 'Segoe UI', sans-serif",
  mono: FONTS_BASE.mono,
};

/** Typography stack — distinctive, not system-font slop. Proxy: в обложке «Пульт» — Commissioner. */
export const FONTS: typeof FONTS_BASE = new Proxy(FONTS_BASE, {
  get(target, prop: string) {
    const key = prop as keyof typeof FONTS_BASE;
    if (currentSkin() === 'pult') return FONTS_PULT[key] ?? target[key];
    return target[key];
  },
});

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

