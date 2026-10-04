import type {
  InvolvementFactCell, InvolvementFactMonth, InvolvementFactRole, InvolvementFactTeam,
} from '../types/api';
import { formatInvolvement, formatQuarter } from './personalSettings';

export interface QuarterRef {
  year: number;
  quarter: number;
}

const MONTHS = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
];

/** Пояснения формулы — для подсказок к заголовкам и подписи «факт». */
export const FACT_FORMULA =
  'Доля часов на задачах вида «Проекты и развитие» среди всех списанных часов';
export const LOGGED_OF_NORM_FORMULA =
  'Сколько часов списано от нормы рабочего времени (календарь минус отсутствия). '
  + 'Если списано мало, факту вовлечённости верить нельзя';

function currentQuarter(today: Date): QuarterRef {
  return { year: today.getFullYear(), quarter: Math.floor(today.getMonth() / 3) + 1 };
}

function previous({ year, quarter }: QuarterRef): QuarterRef {
  return quarter > 1 ? { year, quarter: quarter - 1 } : { year: year - 1, quarter: 4 };
}

export function lastCompletedQuarter(today: Date): QuarterRef {
  return previous(currentQuarter(today));
}

/** Выбор квартала отчёта: текущий (идёт) и завершённые — по убыванию. */
export function quarterOptions(today: Date, count = 8): { value: string; label: string }[] {
  const out: { value: string; label: string }[] = [];
  let q = currentQuarter(today);
  for (let i = 0; i < count; i += 1) {
    out.push({
      value: `${q.year}-${q.quarter}`,
      label: formatQuarter(q.year, q.quarter) + (i === 0 ? ' (идёт)' : ''),
    });
    q = previous(q);
  }
  return out;
}

export function monthLabel(month: number): string {
  return MONTHS[month - 1] ?? String(month);
}

/** Подсказка к «факт N%» в справочнике. */
export function factHint(role: InvolvementFactRole | undefined, year: number, quarter: number): string {
  const period = formatQuarter(year, quarter);
  if (!role || role.total.fact == null) return `За ${period} списаний нет`;
  return `${period} · ${role.people} чел. · списано от нормы ${formatInvolvement(role.total.logged_of_norm)}`;
}

const hours = (h: number) => `${Math.round(h)} ч`;

/** Подсказка к ячейке отчёта: из каких часов получился процент. */
export function cellHint(c: InvolvementFactCell): string {
  return `На проектных задачах ${hours(c.project_hours)} из ${hours(c.logged_hours)} списанных`
    + ` · норма ${hours(c.norm_hours)}`;
}

export type FactRow =
  | { kind: 'person'; key: string; name: string; role: string; months: InvolvementFactMonth[]; total: InvolvementFactCell }
  | { kind: 'role'; key: string; role: string; people: number; months: InvolvementFactMonth[]; total: InvolvementFactCell };

/** Строки таблицы отчёта: люди роли, за ними — «Среднее по роли». */
export function factTableRows(team: InvolvementFactTeam): FactRow[] {
  return team.roles.flatMap((r): FactRow[] => [
    ...team.people
      .filter((p) => p.role === r.role)
      .map((p): FactRow => ({
        kind: 'person', key: p.employee_id, name: p.name, role: p.role, months: p.months, total: p.total,
      })),
    { kind: 'role', key: `role:${r.role}`, role: r.role, people: r.people, months: r.months, total: r.total },
  ]);
}
