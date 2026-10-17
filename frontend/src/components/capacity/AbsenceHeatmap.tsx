import { Tooltip } from 'antd';
import dayjs from 'dayjs';
import { useAppTheme } from '../../contexts/ThemeContext';
import { DARK_THEME } from '../../utils/constants';
import type { AbsenceResponse } from '../../types/api';
import { quarterWeeks, weekMonthSpans } from '../../utils/quarterWeeks';
import { deskShortName } from '../../utils/teamDeskView';

const DEFAULT_REASON_COLOR = '#8c8c8c';

const QUARTER_MONTHS: Record<number, number[]> = {
  1: [1, 2, 3], 2: [4, 5, 6], 3: [7, 8, 9], 4: [10, 11, 12],
};

const MONTH_NAMES = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
];

interface Props {
  year: number;
  quarter: number;
  employees: Array<{ id: string; display_name: string }>;
  absences: AbsenceResponse[];
  /**
   * Компактный вид скина для узкой колонки: недели квартала вместо дней,
   * в ячейке недели — семь полосок-дней цвета причины, короткие имена.
   */
  compact?: boolean;
}

const ddmm = (iso: string) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;

export default function AbsenceHeatmap({ year, quarter, employees, absences, compact = false }: Props) {
  const { mode } = useAppTheme();
  const isLight = mode === 'light';

  const months = QUARTER_MONTHS[quarter] ?? [];
  if (months.length === 0) return null;

  const start = dayjs(`${year}-${String(months[0]).padStart(2, '0')}-01`);
  const end = dayjs(`${year}-${String(months[months.length - 1]).padStart(2, '0')}-01`).endOf('month');
  const days: dayjs.Dayjs[] = [];
  for (let d = start; d.isBefore(end) || d.isSame(end, 'day'); d = d.add(1, 'day')) {
    days.push(d);
  }

  const byEmployee = new Map<string, AbsenceResponse[]>();
  for (const a of absences) {
    const arr = byEmployee.get(a.employee_id) ?? [];
    arr.push(a);
    byEmployee.set(a.employee_id, arr);
  }

  const reasonForDay = (list: AbsenceResponse[] | undefined, d: dayjs.Dayjs): AbsenceResponse | null => {
    if (!list) return null;
    for (const a of list) {
      if (d.isBefore(dayjs(a.start_date))) continue;
      if (d.isAfter(dayjs(a.end_date))) continue;
      return a;
    }
    return null;
  };

  // Палитра ячеек: тёмная и светлая.
  const palette = isLight
    ? {
        // Скин переопределяет переменными --abs-*; у Aurora light их нет.
        weekendBg: 'var(--abs-weekend-bg, #dde3ec)',
        emptyBg: 'var(--abs-empty-bg, #eef2f7)',
        cellBorder: 'var(--abs-cell-border, rgba(195,203,217,0.5))',
        monthSep: 'var(--abs-month-sep, #c3cbd9)',
        monthLabel: 'var(--abs-month-label, #3f4860)',
        dayHeader: 'var(--abs-day-header, #5d6680)',
        weekendHeader: 'var(--abs-weekend-header, #7a8298)',
        nameColor: 'var(--abs-name, #2a3142)',
      }
    : {
        weekendBg: 'rgba(255,255,255,0.03)',
        emptyBg: 'rgba(255,255,255,0.06)',
        cellBorder: 'transparent',
        monthSep: 'rgba(255,255,255,0.18)',
        monthLabel: '#b8c6e0',
        dayHeader: '#c0c8d4',
        weekendHeader: '#6b7a94',
        nameColor: DARK_THEME.textPrimary,
      };

  // Группируем дни по месяцам — чтобы рендерить per-месяц блоки с заголовком + сепаратором.
  const monthGroups = months.map((m) => {
    const monthDays = days.filter((d) => d.month() + 1 === m);
    return { month: m, days: monthDays };
  });

  const cell = 18;
  const nameColWidth = 180;

  // Уникальные причины для легенды
  const uniqueReasons = new Map<string, string>();
  for (const a of absences) {
    if (!uniqueReasons.has(a.reason_label)) {
      uniqueReasons.set(a.reason_label, a.reason_color ?? DEFAULT_REASON_COLOR);
    }
  }

  if (compact) {
    const weeks = quarterWeeks(year, quarter);
    const spans = weekMonthSpans(weeks);
    return (
      <div className="tdc-abs">
        <div
          className="tdc-abs-grid"
          style={{ gridTemplateColumns: `var(--tdc-abs-name-w, 96px) repeat(${weeks.length}, minmax(0, 1fr))` }}
        >
          <span />
          {spans.map((s, idx) => (
            <span key={`m-${idx}`} className="tdc-abs-month" style={{ gridColumn: `span ${s.span}` }}>
              {MONTH_NAMES[s.month - 1]}
            </span>
          ))}
          {employees.map((e) => {
            const list = byEmployee.get(e.id);
            return (
              <div key={`row-${e.id}`} style={{ display: 'contents' }}>
                <span className="tdc-abs-name" title={e.display_name}>{deskShortName(e.display_name)}</span>
                {weeks.map((w) => {
                  const marks = w.days.map((d) => (d.inQuarter ? reasonForDay(list, dayjs(d.iso)) : null));
                  const hits = [...new Set(marks.filter((a): a is AbsenceResponse => a != null))];
                  const lines = hits.length
                    ? hits.map((a) => `${a.reason_label}, ${dayjs(a.start_date).format('DD.MM')}–${dayjs(a.end_date).format('DD.MM')}`)
                    : [`неделя ${ddmm(w.days[0].iso)}–${ddmm(w.days[6].iso)}, отсутствий нет`];
                  return (
                    <Tooltip
                      key={`${e.id}-${w.start}`}
                      title={<div>{e.display_name}{lines.map((l) => <div key={l}>{l}</div>)}</div>}
                      mouseEnterDelay={0.3}
                    >
                      <span className="tdc-abs-week" role="img" aria-label={`${e.display_name}: ${lines.join('; ')}`}>
                        {w.days.map((d, i) => (
                          <span
                            key={d.iso}
                            className={`tdc-abs-day${d.inQuarter ? '' : ' is-out'}`}
                            style={marks[i] ? { background: marks[i]!.reason_color ?? DEFAULT_REASON_COLOR } : undefined}
                          />
                        ))}
                      </span>
                    </Tooltip>
                  );
                })}
              </div>
            );
          })}
        </div>
        {uniqueReasons.size > 0 && (
          <div className="tdc-abs-legend">
            {Array.from(uniqueReasons.entries()).map(([label, color]) => (
              <span key={label}>
                <span className="tdc-abs-legend-sq" style={{ background: color }} />
                {label}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div style={{ overflowX: 'auto', marginBottom: 12 }}>
      {/* Заголовки месяцев */}
      <div style={{ display: 'flex', marginLeft: nameColWidth, marginBottom: 4 }}>
        {monthGroups.map((g, idx) => (
          <div
            key={`mh-${g.month}`}
            style={{
              width: g.days.length * (cell + 1),
              flexShrink: 0,
              fontSize: 11,
              fontWeight: 600,
              color: palette.monthLabel,
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              borderLeft: idx === 0 ? 'none' : `1px solid ${palette.monthSep}`,
              paddingLeft: idx === 0 ? 0 : 4,
            }}
          >
            {MONTH_NAMES[g.month - 1]} {year}
          </div>
        ))}
      </div>

      {/* Сетка дней */}
      <div style={{ display: 'inline-grid', gridTemplateColumns: `${nameColWidth}px repeat(${days.length}, ${cell}px)`, gap: 1 }}>
        <div />
        {days.map((d) => {
          const isMonthStart = d.date() === 1;
          const weekend = d.day() === 0 || d.day() === 6;
          return (
            <div
              key={`h-${d.format('YYYY-MM-DD')}`}
              style={{
                fontSize: 9,
                textAlign: 'center',
                color: weekend ? palette.weekendHeader : palette.dayHeader,
                borderLeft: isMonthStart && d.month() + 1 !== months[0] ? `1px solid ${palette.monthSep}` : 'none',
              }}
            >
              {d.date() === 1 || d.date() % 5 === 0 ? d.date() : ''}
            </div>
          );
        })}
        {employees.map((e) => {
          const list = byEmployee.get(e.id);
          return (
            <div key={`row-${e.id}`} style={{ display: 'contents' }}>
              <div style={{
                fontSize: 12, paddingRight: 8, color: palette.nameColor,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {e.display_name}
              </div>
              {days.map((d) => {
                const a = reasonForDay(list, d);
                const weekend = d.day() === 0 || d.day() === 6;
                const isMonthStart = d.date() === 1;
                const bg = a
                  ? (a.reason_color ?? DEFAULT_REASON_COLOR)
                  : (weekend ? palette.weekendBg : palette.emptyBg);
                const tip = a
                  ? `${e.display_name}: ${a.reason_label}, ${dayjs(a.start_date).format('DD.MM')}–${dayjs(a.end_date).format('DD.MM')}`
                  : `${e.display_name} · ${d.format('DD.MM')}`;
                return (
                  <Tooltip key={`${e.id}-${d.format('YYYY-MM-DD')}`} title={tip} mouseEnterDelay={0.3}>
                    <div style={{
                      height: 18,
                      background: bg,
                      borderRadius: 2,
                      border: `1px solid ${palette.cellBorder}`,
                      borderLeft: isMonthStart && d.month() + 1 !== months[0]
                        ? `1px solid ${palette.monthSep}`
                        : `1px solid ${palette.cellBorder}`,
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
          marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 12,
          fontSize: 11, color: palette.monthLabel,
        }}>
          {Array.from(uniqueReasons.entries()).map(([label, color]) => (
            <span key={label} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <span style={{
                display: 'inline-block', width: 12, height: 12, borderRadius: 2,
                background: color, border: `1px solid ${palette.cellBorder}`,
              }} />
              {label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
