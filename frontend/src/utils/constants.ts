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

/** «Тёплая» — тёплая палитра данных: синий, бирюза, охра, хвоя, слива, терракота. */
const CHART_COLORS_WARM: ChartColorsShape = {
  blue: '#3F6CA8',
  green: '#3F7D4E',
  orange: '#D9822B',
  red: '#B5502A',
  purple: '#8A4F7D',
  cyan: '#2E8B8B',
  cyanSecondary: '#5E9E98',
  yellow: '#B7791F',
  neutral: '#8A8174',
};

/** Палитры графиков «скинов» поверх Aurora light — ключ = `<html data-skin>`. */
const SKIN_CHART_COLORS: Record<string, ChartColorsShape> = {
  warm: CHART_COLORS_WARM,
};

/** Runtime-aware chart colors. Mirrors DARK_THEME Proxy strategy. */
export const CHART_COLORS: ChartColorsShape = new Proxy(CHART_COLORS_CLASSIC, {
  get(target, prop: string) {
    if (typeof document === 'undefined') return target[prop as keyof ChartColorsShape];
    const root = document.documentElement;
    if (root.getAttribute('data-theme') !== 'aurora') {
      return target[prop as keyof ChartColorsShape];
    }
    const skin = SKIN_CHART_COLORS[root.getAttribute('data-skin') ?? ''];
    if (skin) return skin[prop as keyof ChartColorsShape] ?? target[prop as keyof ChartColorsShape];
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

/* «Тёплая» — тёплый камень + белые поверхности, хвойный акцент. Только сплошные цвета.
 * Контраст на белом: textPrimary 14:1, textSecondary 9:1, textMuted 5.9:1, textHint 4.5:1. */
const WARM_TOKENS: DarkThemeShape = {
  pageBg: '#EFEBE5',
  sidebarBg: '#EFEBE5',
  cardBg: '#FFFFFF',
  darkAccent: '#F5F1EA',
  border: '#E3DDD3',
  darkRows: '#FAF8F4',
  cyanPrimary: '#2F6B5A',
  cyanSecondary: '#3F6CA8',
  yellow: '#8A5A10',
  amber: '#8A5A10',
  amberDim: '#7A4E0C',
  danger: '#A0461F',
  success: '#356F45',
  textPrimary: '#2A2620',
  textSecondary: '#4A443A',
  textMuted: '#6B6358',
  textHint: '#6B6358',
  textDim: '#6B6358',
};

/** Наборы токенов «скинов» поверх Aurora light — ключ = `<html data-skin>`. */
const SKIN_TOKENS: Record<string, DarkThemeShape> = {
  warm: WARM_TOKENS,
};

/** Runtime-aware Dark theme tokens.
 *  Reads `<html data-theme="aurora" data-mode="dark|light">` on every access:
 *  - classic: returns DARK_THEME_CLASSIC value
 *  - aurora-dark: returns AURORA_DARK_TOKENS value
 *  - aurora-light: returns AURORA_LIGHT_TOKENS value
 *  - skin (`data-skin="warm"` поверх aurora-light): returns SKIN_TOKENS[skin] value
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
    const skin = SKIN_TOKENS[root.getAttribute('data-skin') ?? ''];
    if (skin) return skin[prop as keyof DarkThemeShape] ?? target[prop as keyof DarkThemeShape];
    const mode = root.getAttribute('data-mode');
    const pool = mode === 'light' ? AURORA_LIGHT_TOKENS : AURORA_DARK_TOKENS;
    return pool[prop as keyof DarkThemeShape] ?? target[prop as keyof DarkThemeShape];
  },
});

export type AppTheme = 'aurora-dark' | 'aurora-light' | 'warm-light';

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

export interface AppThemeDef {
  label: string;
  /** Значение `<html data-mode>`. */
  mode: 'dark' | 'light';
  /** Значение `<html data-skin>`: стиль поверх Aurora light. У самих тем Aurora — нет. */
  skin?: string;
  tokens: ThemeTokens;
}

export const APP_THEMES: Record<AppTheme, AppThemeDef> = {
  'aurora-dark': {
    label: 'Aurora тёмная',
    mode: 'dark',
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
    mode: 'light',
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
  'warm-light': {
    label: 'Тёплая',
    mode: 'light',
    skin: 'warm',
    tokens: {
      pageBg: WARM_TOKENS.pageBg,
      sidebarBg: WARM_TOKENS.sidebarBg,
      cardBg: WARM_TOKENS.cardBg,
      darkAccent: WARM_TOKENS.darkAccent,
      border: WARM_TOKENS.border,
      darkRows: WARM_TOKENS.darkRows,
      primary: WARM_TOKENS.cyanPrimary,
      primarySecondary: WARM_TOKENS.cyanSecondary,
      textPrimary: WARM_TOKENS.textPrimary,
      textSecondary: WARM_TOKENS.textSecondary,
      textMuted: WARM_TOKENS.textMuted,
      textHint: WARM_TOKENS.textHint,
    },
  },
};

interface FontsShape {
  display: string;
  body: string;
  mono: string;
}

/** Typography stack — distinctive, not system-font slop */
const FONTS_BASE: FontsShape = {
  display: "'Fraunces', 'Georgia', serif",
  body: "'Manrope', -apple-system, 'Segoe UI', sans-serif",
  mono: "'JetBrains Mono', ui-monospace, 'SF Mono', 'Consolas', monospace",
};

const ONEST = "'Onest', -apple-system, 'Segoe UI', sans-serif";
/** У «Тёплой» один шрифт на всё: цифры выравнивает tabular-nums, а не моноширинный. */
const SKIN_FONTS: Record<string, FontsShape> = {
  warm: { display: ONEST, body: ONEST, mono: ONEST },
};

/** Runtime-aware fonts: inline `fontFamily: FONTS.mono` follows `<html data-skin>` like DARK_THEME. */
export const FONTS: Readonly<FontsShape> = new Proxy(FONTS_BASE, {
  get(target, prop: string) {
    if (typeof document === 'undefined') return target[prop as keyof FontsShape];
    const skin = SKIN_FONTS[document.documentElement.getAttribute('data-skin') ?? ''];
    return skin?.[prop as keyof FontsShape] ?? target[prop as keyof FontsShape];
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

