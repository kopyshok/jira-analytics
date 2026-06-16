import { Tooltip } from 'antd';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { MONTH_NAMES } from '../../utils/constants';
import type { DeskAbsence, TeamAbsencesData } from '../../types/desk';

const DEFAULT_REASON_COLOR = 'var(--ink-4)';
const QUARTER_MONTHS: Record<number, number[]> = {
  1: [1, 2, 3], 2: [4, 5, 6], 3: [7, 8, 9], 4: [10, 11, 12],
};
const MONTH_GEN = [
  '', 'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
];

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

interface DayCol {
  iso: string;
  month: number;
  day: number;
  weekend: boolean;
}

export default function TeamAbsencesWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<TeamAbsencesData>(token, 'team_absences');
  const employees = data?.employees ?? [];
  const absences = data?.absences ?? [];
  const year = data?.year ?? new Date().getFullYear();
  const quarter = data?.quarter ?? 1;
  const months = QUARTER_MONTHS[quarter] ?? [];

  // Колонки дней квартала.
  const cols: DayCol[] = [];
  for (const m of months) {
    const last = new Date(year, m, 0).getDate();
    for (let d = 1; d <= last; d += 1) {
      const iso = `${year}-${pad(m)}-${pad(d)}`;
      const dow = new Date(iso).getDay();
      cols.push({ iso, month: m, day: d, weekend: dow === 0 || dow === 6 });
    }
  }
  const monthSpans = months.map((m) => ({
    month: m,
    span: cols.filter((c) => c.month === m).length,
  }));

  const byEmployee = new Map<string, DeskAbsence[]>();
  for (const a of absences) {
    const arr = byEmployee.get(a.employee_id) ?? [];
    arr.push(a);
    byEmployee.set(a.employee_id, arr);
  }

  const absenceForDay = (list: DeskAbsence[] | undefined, iso: string): DeskAbsence | null => {
    if (!list) return null;
    for (const a of list) {
      if (iso >= a.start_date.slice(0, 10) && iso <= a.end_date.slice(0, 10)) return a;
    }
    return null;
  };

  // Легенда — уникальные причины.
  const uniqueReasons = new Map<string, string>();
  for (const a of absences) {
    if (!uniqueReasons.has(a.reason_label)) {
      uniqueReasons.set(a.reason_label, a.reason_color ?? DEFAULT_REASON_COLOR);
    }
  }

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={employees.length === 0}
      emptyText="Нет сотрудников"
    >
      <table className="desk-absence-table">
        <thead>
          <tr>
            <th className="name-cell" style={{ width: 140 }} />
            {monthSpans.map((g) => (
              <th key={`m-${g.month}`} className="month-header-cell" colSpan={g.span}>
                {MONTH_NAMES[g.month]} {year}
              </th>
            ))}
          </tr>
          <tr>
            <th />
            {cols.map((c) => (
              <th key={`d-${c.iso}`}>{c.day === 1 || c.day % 5 === 0 ? c.day : ''}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {employees.map((e) => {
            const list = byEmployee.get(e.id);
            return (
              <tr key={e.id}>
                <td className="name-cell">{e.display_name}</td>
                {cols.map((c) => {
                  const a = absenceForDay(list, c.iso);
                  const classes = ['day-cell'];
                  if (!a && c.weekend) classes.push('weekend');
                  const style = a ? { background: a.reason_color ?? DEFAULT_REASON_COLOR } : undefined;
                  const tip = a
                    ? `${a.reason_label}: ${Number(a.start_date.slice(8, 10))} ${MONTH_GEN[Number(a.start_date.slice(5, 7))]} – ${Number(a.end_date.slice(8, 10))} ${MONTH_GEN[Number(a.end_date.slice(5, 7))]} ${year} · ${e.display_name}`
                    : `${c.day} ${MONTH_GEN[c.month]} ${year}`;
                  return (
                    <Tooltip key={`${e.id}-${c.iso}`} title={tip} mouseEnterDelay={0.25}>
                      <td className={classes.join(' ')} style={style} />
                    </Tooltip>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>

      {uniqueReasons.size > 0 && (
        <div className="desk-absence-legend">
          {[...uniqueReasons.entries()].map(([label, color]) => (
            <span key={label} className="desk-legend-item">
              <span className="desk-legend-swatch" style={{ background: color }} />
              {label}
            </span>
          ))}
        </div>
      )}
    </WidgetShell>
  );
}
