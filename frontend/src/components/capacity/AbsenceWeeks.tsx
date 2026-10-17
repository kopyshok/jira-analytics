import { Tooltip } from 'antd';
import dayjs from 'dayjs';
import { DARK_THEME } from '../../utils/constants';
import type { AbsenceResponse } from '../../types/api';
import { absenceInWeek, quarterWeeks } from './absenceWeeksMath';

const DEFAULT_REASON_COLOR = '#8c8c8c';
const MONTH_SHORT = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];

interface Props {
  year: number;
  quarter: number;
  employees: Array<{ id: string; display_name: string }>;
  absences: AbsenceResponse[];
}

/**
 * Отсутствия за квартал одной строкой на человека, клетка — неделя.
 * Для узкой боковой панели: весь квартал виден без прокрутки
 * (по дням — теплокарта `AbsenceHeatmap` на экране ресурсов).
 */
export default function AbsenceWeeks({ year, quarter, employees, absences }: Props) {
  const { qStart, qEnd, weeks } = quarterWeeks(year, quarter);

  const byEmployee = new Map<string, AbsenceResponse[]>();
  for (const a of absences) {
    const list = byEmployee.get(a.employee_id) ?? [];
    list.push(a);
    byEmployee.set(a.employee_id, list);
  }

  // Подпись месяца — над неделей, в которую попадает его первое число.
  const monthAt = weeks.map((w, i) => {
    const sunday = w.add(6, 'day');
    for (let m = 0; m < 3; m++) {
      const first = qStart.add(m, 'month');
      if (!first.isBefore(w, 'day') && !first.isAfter(sunday, 'day')) return MONTH_SHORT[first.month()];
    }
    return i === 0 ? MONTH_SHORT[qStart.month()] : '';
  });

  const shownIds = new Set(employees.map((e) => e.id));
  const reasons = new Map<string, string>();
  for (const a of absences) {
    if (!shownIds.has(a.employee_id)) continue;
    if (dayjs(a.end_date).isBefore(qStart, 'day') || dayjs(a.start_date).isAfter(qEnd, 'day')) continue;
    if (!reasons.has(a.reason_label)) reasons.set(a.reason_label, a.reason_color ?? DEFAULT_REASON_COLOR);
  }

  const grid = { display: 'grid', gridTemplateColumns: `minmax(90px, 132px) repeat(${weeks.length}, minmax(9px, 1fr))`, gap: 2, alignItems: 'center' } as const;

  return (
    <div data-testid="absence-weeks">
      <div style={{ ...grid, marginBottom: 3 }}>
        <span />
        {monthAt.map((m, i) => (
          <span key={i} style={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: '0.06em', color: DARK_THEME.textMuted, whiteSpace: 'nowrap', overflow: 'visible' }}>
            {m}
          </span>
        ))}
      </div>
      {employees.map((e) => {
        const list = byEmployee.get(e.id);
        return (
          <div key={e.id} style={{ ...grid, marginBottom: 2 }}>
            <span title={e.display_name} style={{ fontSize: 12, color: DARK_THEME.textPrimary, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', paddingRight: 6 }}>
              {e.display_name}
            </span>
            {weeks.map((w) => {
              const a = absenceInWeek(list, w, qStart, qEnd);
              const tip = a
                ? `${e.display_name}: ${a.reason_label}, ${dayjs(a.start_date).format('DD.MM')}–${dayjs(a.end_date).format('DD.MM')}`
                : `${e.display_name} · неделя с ${w.format('DD.MM')}`;
              return (
                <Tooltip key={w.format('YYYY-MM-DD')} title={tip} mouseEnterDelay={0.3}>
                  <span style={{
                    height: 14,
                    borderRadius: 2,
                    background: a ? (a.reason_color ?? DEFAULT_REASON_COLOR) : 'var(--tile-bg, rgba(255,255,255,0.06))',
                    border: '1px solid var(--hairline, rgba(255,255,255,0.08))',
                  }} />
                </Tooltip>
              );
            })}
          </div>
        );
      })}
      {reasons.size > 0 ? (
        <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 10, fontSize: 11, color: DARK_THEME.textSecondary }}>
          {Array.from(reasons.entries()).map(([label, color]) => (
            <span key={label} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, background: color, display: 'inline-block' }} />
              {label}
            </span>
          ))}
        </div>
      ) : (
        <div style={{ marginTop: 8, fontSize: 11, color: DARK_THEME.textMuted }}>Отсутствий в квартале нет</div>
      )}
    </div>
  );
}
