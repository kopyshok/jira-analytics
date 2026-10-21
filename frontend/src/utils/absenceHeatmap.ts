import dayjs from 'dayjs';
import type { AbsenceResponse } from '../types/api';
import { QUARTER_MONTHS } from './constants';

/** День квартала на карте отсутствий — всё, что клетке нужно для отрисовки. */
export interface HeatmapDay {
  iso: string;
  /** Месяц 1–12. */
  month: number;
  weekend: boolean;
  /** Первое число второго и третьего месяца — у клетки разделитель слева. */
  monthStart: boolean;
  /** Подпись над столбцом: 1-е и каждое пятое число, иначе пусто. */
  label: number | '';
}

/** Дни квартала по порядку. */
export function quarterDays(year: number, quarter: number): HeatmapDay[] {
  const months = QUARTER_MONTHS[quarter] ?? [];
  if (months.length === 0) return [];
  const start = dayjs(`${year}-${String(months[0]).padStart(2, '0')}-01`);
  const end = start.add(months.length, 'month');
  const days: HeatmapDay[] = [];
  for (let d = start; d.isBefore(end, 'day'); d = d.add(1, 'day')) {
    const date = d.date();
    days.push({
      iso: d.format('YYYY-MM-DD'),
      month: d.month() + 1,
      weekend: d.day() === 0 || d.day() === 6,
      monthStart: date === 1 && d.month() + 1 !== months[0],
      label: date === 1 || date % 5 === 0 ? date : '',
    });
  }
  return days;
}

/**
 * Отсутствие на каждый день квартала по сотрудникам: строка — массив по дням
 * квартала, в пустой день — undefined. При пересечении день остаётся за
 * отсутствием, которое в списке раньше. Сотрудника без отсутствий в квартале
 * в результате нет.
 */
export function absenceCellsByEmployee(
  absences: AbsenceResponse[],
  days: HeatmapDay[],
): Map<string, (AbsenceResponse | undefined)[]> {
  const cells = new Map<string, (AbsenceResponse | undefined)[]>();
  if (days.length === 0) return cells;
  const first = dayjs(days[0].iso);
  const last = days.length - 1;
  for (const a of absences) {
    const from = Math.max(0, dayjs(a.start_date).diff(first, 'day'));
    const to = Math.min(last, dayjs(a.end_date).diff(first, 'day'));
    if (from > to) continue;
    let row = cells.get(a.employee_id);
    if (!row) {
      row = new Array<AbsenceResponse | undefined>(days.length).fill(undefined);
      cells.set(a.employee_id, row);
    }
    for (let i = from; i <= to; i++) row[i] ??= a;
  }
  return cells;
}

/** Текст подсказки над клеткой. */
export function absenceCellTip(name: string, day: HeatmapDay, absence: AbsenceResponse | undefined): string {
  return absence
    ? `${name}: ${absence.reason_label}, ${dayjs(absence.start_date).format('DD.MM')}–${dayjs(absence.end_date).format('DD.MM')}`
    : `${name} · ${dayjs(day.iso).format('DD.MM')}`;
}
