import { Tooltip } from 'antd';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { fmtShortRange } from './format';
import { DARK_THEME, MONTH_NAMES } from '../../utils/constants';
import type { DeskAbsence, TeamAbsencesData } from '../../types/desk';

const DEFAULT_REASON_COLOR = '#8c8c8c';
const QUARTER_MONTHS: Record<number, number[]> = {
  1: [1, 2, 3], 2: [4, 5, 6], 3: [7, 8, 9], 4: [10, 11, 12],
};

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

/** Все дни квартала как ISO-строки YYYY-MM-DD. */
function quarterDays(year: number, months: number[]): string[] {
  const out: string[] = [];
  for (const m of months) {
    const last = new Date(year, m, 0).getDate();
    for (let d = 1; d <= last; d += 1) out.push(`${year}-${pad(m)}-${pad(d)}`);
  }
  return out;
}

function isWeekend(iso: string): boolean {
  const dow = new Date(iso).getDay();
  return dow === 0 || dow === 6;
}

export default function TeamAbsencesWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<TeamAbsencesData>(token, 'team_absences');
  const employees = data?.employees ?? [];
  const absences = data?.absences ?? [];
  const year = data?.year ?? new Date().getFullYear();
  const quarter = data?.quarter ?? 1;
  const months = QUARTER_MONTHS[quarter] ?? [];

  const days = quarterDays(year, months);
  const cell = 16;
  const nameColWidth = 160;

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

  const monthGroups = months.map((m) => ({
    month: m,
    days: days.filter((d) => Number(d.slice(5, 7)) === m),
  }));

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={employees.length === 0}
      emptyText="Нет сотрудников"
    >
      <div style={{ overflowX: 'auto' }}>
        {/* Заголовки месяцев */}
        <div style={{ display: 'flex', marginLeft: nameColWidth, marginBottom: 4 }}>
          {monthGroups.map((g, idx) => (
            <div
              key={`mh-${g.month}`}
              style={{
                width: g.days.length * (cell + 1),
                fontSize: 11,
                fontWeight: 600,
                color: DARK_THEME.textSecondary,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                borderLeft: idx === 0 ? 'none' : `1px solid ${DARK_THEME.border}`,
                paddingLeft: idx === 0 ? 0 : 4,
              }}
            >
              {MONTH_NAMES[g.month]} {year}
            </div>
          ))}
        </div>

        {/* Сетка дней */}
        <div style={{
          display: 'inline-grid',
          gridTemplateColumns: `${nameColWidth}px repeat(${days.length}, ${cell}px)`,
          gap: 1,
        }}>
          <div />
          {days.map((iso) => {
            const day = Number(iso.slice(8, 10));
            const monthStart = day === 1;
            return (
              <div
                key={`h-${iso}`}
                style={{
                  fontSize: 9,
                  textAlign: 'center',
                  color: isWeekend(iso) ? DARK_THEME.textDim : DARK_THEME.textMuted,
                  borderLeft: monthStart && Number(iso.slice(5, 7)) !== months[0]
                    ? `1px solid ${DARK_THEME.border}` : 'none',
                }}
              >
                {day === 1 || day % 5 === 0 ? day : ''}
              </div>
            );
          })}
          {employees.map((e) => {
            const list = byEmployee.get(e.id);
            return (
              <div key={`row-${e.id}`} style={{ display: 'contents' }}>
                <div style={{
                  fontSize: 12, paddingRight: 8, color: DARK_THEME.textPrimary,
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {e.display_name}
                </div>
                {days.map((iso) => {
                  const a = absenceForDay(list, iso);
                  const weekend = isWeekend(iso);
                  const monthStart = Number(iso.slice(8, 10)) === 1;
                  const bg = a
                    ? (a.reason_color ?? DEFAULT_REASON_COLOR)
                    : (weekend ? 'rgba(255,255,255,0.03)' : 'rgba(255,255,255,0.06)');
                  // Подсказка: причина и период разнесены для читаемости.
                  const tip = a
                    ? `${a.reason_label}\n${fmtShortRange(a.start_date, a.end_date)}`
                    : `${e.display_name} · ${iso.slice(8, 10)}.${iso.slice(5, 7)}`;
                  return (
                    <Tooltip
                      key={`${e.id}-${iso}`}
                      title={<span style={{ whiteSpace: 'pre-line' }}>{tip}</span>}
                      mouseEnterDelay={0.3}
                    >
                      <div style={{
                        height: cell,
                        background: bg,
                        borderRadius: 2,
                        borderLeft: monthStart && Number(iso.slice(5, 7)) !== months[0]
                          ? `1px solid ${DARK_THEME.border}` : 'none',
                      }} />
                    </Tooltip>
                  );
                })}
              </div>
            );
          })}
        </div>

        {/* Легенда */}
        {uniqueReasons.size > 0 && (
          <div style={{
            marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 16,
            fontSize: 11, color: DARK_THEME.textSecondary,
          }}>
            {[...uniqueReasons.entries()].map(([label, color]) => (
              <span key={label} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <span style={{
                  display: 'inline-block', width: 12, height: 12, borderRadius: 2, background: color,
                }} />
                {label}
              </span>
            ))}
          </div>
        )}
      </div>
    </WidgetShell>
  );
}
