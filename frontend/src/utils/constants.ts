import type { EmployeeRole } from '../types/api';

export const EMPLOYEE_ROLE_LABELS: Record<EmployeeRole, string> = {
  analyst: 'Аналитик',
  dev: 'Программист',
  qa: 'Тестировщик',
  other: 'Другое',
};

export const EMPLOYEE_ROLES: EmployeeRole[] = [
  'analyst',
  'dev',
  'qa',
  'other',
];

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
  /** Positive delta (growth, completion) */
  success: '#1D9E75',
  textPrimary: '#e8f0fa',
  textSecondary: '#c5d8ee',
  textMuted: '#8faec8',
  textHint: '#6b8aaa',
  textDim: '#4a6a8a',
} as const;

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

/** Planning-role palette — used on Бэклог/Сценарии pages to color capacity bars,
 *  badges, and role-breakdown segments per backlog item. */
export const ROLE_COLORS = {
  analyst: '#4db8e8',
  dev:     '#00c9c8',
  qa:      '#EF9F27',
  opo:     '#7F77DD',
} as const;

export const ROLE_LABELS = {
  analyst: 'Аналитик',
  dev:     'Программист',
  qa:      'Тестировщик',
  opo:     'Запуск (ОПЭ)',
} as const;

export const ROLE_SHORT = {
  analyst: 'АН',
  dev:     'ПР',
  qa:      'ТС',
  opo:     'ОПЭ',
} as const;

export type PlanningRole = keyof typeof ROLE_COLORS;
