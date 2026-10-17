import { Tooltip } from 'antd';
import dayjs from 'dayjs';
import { useAppTheme } from '../../contexts/ThemeContext';
import { DARK_THEME } from '../../utils/constants';
import { solidFill } from '../../utils/readableColor';
import type { AbsenceResponse } from '../../types/api';

const DEFAULT_REASON_COLOR = '#8c8c8c';

const QUARTER_MONTHS: Record<number, number[]> = {
  1: [1, 2, 3], 2: [4, 5, 6], 3: [7, 8, 9], 4: [10, 11, 12],
};

const MONTH_NAMES = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
];
const MONTH_SHORT = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];

interface Props {
  year: number;
  quarter: number;
  employees: Array<{ id: string; display_name: string }>;
  absences: AbsenceResponse[];
  /** По неделям, во всю ширину колонки: доля отсутствия в неделе (узкая колонка обложки). */
  compact?: boolean;
}

export default function AbsenceHeatmap({ year, quarter, employees, absences, compact = false }: Props) {
  const { mode, skin } = useAppTheme();
  const isLight = mode === 'light';
  // В светлой обложке пастельные цвета причин на белом почти не видны — тот же тон темнее.
  const reasonColor = (c: string | null | undefined) => {
    const color = c ?? DEFAULT_REASON_COLOR;
    return skin ? solidFill(color) : color;
  };

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
        weekendBg: '#dde3ec',
        emptyBg: '#eef2f7',
        cellBorder: 'rgba(195,203,217,0.5)',
        monthSep: '#c3cbd9',
        monthLabel: '#3f4860',
        dayHeader: '#5d6680',
        weekendHeader: '#7a8298',
        nameColor: '#2a3142',
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
      uniqueReasons.set(a.reason_label, reasonColor(a.reason_color));
    }
  }

  if (compact) {
    return (
      <CompactWeeks
        days={days}
        employees={employees}
        byEmployee={byEmployee}
        reasonForDay={reasonForDay}
        reasonColor={reasonColor}
        uniqueReasons={uniqueReasons}
      />
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
                  ? reasonColor(a.reason_color)
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

/**
 * Квартал по неделям: клетка — неделя, заливка — доля рабочих дней отсутствия
 * цветом главной причины недели. Для узких колонок, где по дням не помещается.
 */
function CompactWeeks({
  days, employees, byEmployee, reasonForDay, reasonColor, uniqueReasons,
}: {
  days: dayjs.Dayjs[];
  employees: Array<{ id: string; display_name: string }>;
  byEmployee: Map<string, AbsenceResponse[]>;
  reasonForDay: (list: AbsenceResponse[] | undefined, d: dayjs.Dayjs) => AbsenceResponse | null;
  reasonColor: (c: string | null | undefined) => string;
  uniqueReasons: Map<string, string>;
}) {
  // Недели с понедельника; крайние недели квартала — неполные.
  const weeks: dayjs.Dayjs[][] = [];
  for (const d of days) {
    if (weeks.length === 0 || d.day() === 1) weeks.push([]);
    weeks[weeks.length - 1].push(d);
  }
  // Подпись месяца — над неделями, которые в нём начинаются.
  const monthSpans: { label: string; span: number }[] = [];
  for (const w of weeks) {
    const m = w[0].month();
    const last = monthSpans[monthSpans.length - 1];
    if (last && last.label === MONTH_SHORT[m]) last.span += 1;
    else monthSpans.push({ label: MONTH_SHORT[m], span: 1 });
  }
  const columns = `minmax(80px, 104px) repeat(${weeks.length}, minmax(0, 1fr))`;
  return (
    <div className="abs-weeks">
      <div className="abs-weeks-months" style={{ display: 'grid', gridTemplateColumns: columns, columnGap: 2 }}>
        <span />
        {monthSpans.map((m, i) => (
          <span key={`${m.label}-${i}`} style={{ gridColumn: `span ${m.span}` }}>{m.label}</span>
        ))}
      </div>
      <div className="abs-weeks-grid" style={{ display: 'grid', gridTemplateColumns: columns, gap: '3px 2px', alignItems: 'center' }}>
        {employees.map((e) => {
          const list = byEmployee.get(e.id);
          return (
            <div key={`row-${e.id}`} style={{ display: 'contents' }}>
              <span className="abs-weeks-name" title={e.display_name}>{e.display_name}</span>
              {weeks.map((w) => {
                const workdays = w.filter((d) => d.day() !== 0 && d.day() !== 6);
                const hits = new Map<string, { a: AbsenceResponse; days: number }>();
                for (const d of workdays) {
                  const a = reasonForDay(list, d);
                  if (!a) continue;
                  const cur = hits.get(a.id) ?? { a, days: 0 };
                  cur.days += 1;
                  hits.set(a.id, cur);
                }
                const absent = [...hits.values()].reduce((n, h) => n + h.days, 0);
                const main = [...hits.values()].sort((x, y) => y.days - x.days)[0];
                const share = workdays.length ? absent / workdays.length : 0;
                const tip = [...hits.values()]
                  .map((h) => `${h.a.reason_label}, ${dayjs(h.a.start_date).format('DD.MM')}–${dayjs(h.a.end_date).format('DD.MM')}`)
                  .join('; ');
                return (
                  <Tooltip
                    key={`${e.id}-${w[0].format('YYYY-MM-DD')}`}
                    title={tip ? `${e.display_name}: ${tip}` : `${e.display_name} · неделя с ${w[0].format('DD.MM')}`}
                    mouseEnterDelay={0.3}
                  >
                    <span className="abs-weeks-cell">
                      {main && (
                        <span style={{ width: `${Math.round(share * 100)}%`, background: reasonColor(main.a.reason_color) }} />
                      )}
                    </span>
                  </Tooltip>
                );
              })}
            </div>
          );
        })}
      </div>
      {uniqueReasons.size > 0 && (
        <div className="abs-weeks-legend">
          {Array.from(uniqueReasons.entries()).map(([label, color]) => (
            <span key={label}><i style={{ background: color }} />{label}</span>
          ))}
        </div>
      )}
    </div>
  );
}
