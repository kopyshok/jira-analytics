import { MONTH_NAMES } from './constants';

export type KpiPeriodMode = 'month' | 'quarter' | 'last' | 'custom';

/** Период отчёта KPI: последний месяц плюс сколько месяцев назад считать.
 *
 * Одной парой описываются все режимы: месяц (1), конкретный квартал (3 с
 * концом в последнем месяце квартала), последние N месяцев и произвольный
 * отрезок. Сервер принимает ровно эти два числа.
 */
export interface KpiPeriod {
  year: number;
  month: number;
  months: number;
}

export const QUARTER_LABELS = [
  'I квартал (янв–мар)', 'II квартал (апр–июн)', 'III квартал (июл–сен)', 'IV квартал (окт–дек)',
];

export function quarterOfMonth(month: number): number {
  return Math.floor((month - 1) / 3) + 1;
}

/** Сдвиг периода на один шаг вперёд или назад.
 *
 * Шаг равен длине периода: у квартала стрелки листают кварталы, у месяца —
 * месяцы. Иначе «предыдущий» на квартальном экране показывал бы период,
 * перекрывающийся с текущим на две трети.
 */
export function stepPeriod(period: KpiPeriod, dir: 1 | -1): KpiPeriod {
  const total = period.year * 12 + (period.month - 1) + dir * period.months;
  return { ...period, year: Math.floor(total / 12), month: (total % 12) + 1 };
}

/** Подпись периода — то, что читает руководитель вместо «месяц 9, длина 3». */
export function periodLabel({ year, month, months }: KpiPeriod): string {
  if (months === 1) return `${MONTH_NAMES[month]} ${year}`;
  if (months === 3 && month % 3 === 0) {
    return `${QUARTER_LABELS[quarterOfMonth(month) - 1]} ${year}`;
  }
  const startTotal = year * 12 + (month - 1) - (months - 1);
  const startYear = Math.floor(startTotal / 12);
  const startMonth = (startTotal % 12) + 1;
  const start = startYear === year
    ? MONTH_NAMES[startMonth]
    : `${MONTH_NAMES[startMonth]} ${startYear}`;
  return `${start} — ${MONTH_NAMES[month]} ${year}`;
}

/** Режим, которому соответствует период — по нему подсвечивается переключатель. */
export function modeOf(period: KpiPeriod): KpiPeriodMode {
  if (period.months === 1) return 'month';
  if (period.months === 3 && period.month % 3 === 0) return 'quarter';
  return 'custom';
}

/** Период при переключении режима: месяц-«якорь» сохраняем, длину меняем.
 *
 * Для квартала конечный месяц подтягивается к последнему месяцу того
 * квартала, в котором сейчас стоит якорь, — иначе «квартал» с концом в
 * августе выглядел бы кварталом, им не являясь.
 */
export function periodForMode(period: KpiPeriod, mode: KpiPeriodMode, today = new Date()): KpiPeriod {
  if (mode === 'month') return { ...period, months: 1 };
  if (mode === 'quarter') {
    return { ...period, month: quarterOfMonth(period.month) * 3, months: 3 };
  }
  if (mode === 'last') {
    return { year: today.getFullYear(), month: today.getMonth() + 1, months: 3 };
  }
  return { ...period, months: period.months > 1 ? period.months : 2 };
}
