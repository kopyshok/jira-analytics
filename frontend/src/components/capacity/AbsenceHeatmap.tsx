import { memo, useEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties, MouseEvent } from 'react';
import { Tooltip } from 'antd';
import { useAppTheme, useSkin } from '../../contexts/ThemeContext';
import { DARK_THEME } from '../../utils/constants';
import { absenceCellTip, absenceCellsByEmployee, quarterDays } from '../../utils/absenceHeatmap';
import type { HeatmapDay } from '../../utils/absenceHeatmap';
import type { AbsenceResponse } from '../../types/api';
import './AbsenceHeatmap.css';

const DEFAULT_REASON_COLOR = '#8c8c8c';

const MONTH_NAMES = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
];

const CELL = 18;
const NAME_COL_WIDTH = 180;
/** Задержка подсказки, как у прежней подсказки на клетке. */
const TIP_DELAY_MS = 300;

type Employee = { id: string; display_name: string };
type Cells = Map<string, (AbsenceResponse | undefined)[]>;

interface Props {
  year: number;
  quarter: number;
  employees: Employee[];
  absences: AbsenceResponse[];
}

const cellClass = (d: HeatmapDay) =>
  'absence-heatmap__cell'
  + (d.weekend ? ' absence-heatmap__cell--weekend' : '')
  + (d.monthStart ? ' absence-heatmap__cell--month-start' : '');

/**
 * Строки сотрудников. Отдельно и под memo: наведение и перерисовки страницы
 * не трогают тысячи клеток, пока не поменялись сами данные.
 */
const HeatmapRows = memo(function HeatmapRows({ employees, days, cells }: {
  employees: Employee[];
  days: HeatmapDay[];
  cells: Cells;
}) {
  const classes = days.map(cellClass);
  return employees.map((e, row) => {
    const list = cells.get(e.id);
    return (
      <div key={e.id} data-row={row} className="absence-heatmap__row">
        <div className="absence-heatmap__name">{e.display_name}</div>
        {days.map((d, i) => {
          const a = list?.[i];
          return (
            <div
              key={d.iso}
              data-day={i}
              className={classes[i]}
              style={a ? { background: a.reason_color ?? DEFAULT_REASON_COLOR } : undefined}
            />
          );
        })}
      </div>
    );
  });
});

type Hover = { row: number; day: number; left: number; top: number };

function AbsenceHeatmap({ year, quarter, employees, absences }: Props) {
  const { mode } = useAppTheme();
  const isLight = mode === 'light';
  const skin = useSkin();

  const days = useMemo(() => quarterDays(year, quarter), [year, quarter]);
  const cells = useMemo(() => absenceCellsByEmployee(absences, days), [absences, days]);

  // Одна подсказка на всю карту: клетка под курсором ищется по всплывшему
  // событию, а не своя подсказка у каждой клетки.
  const [hover, setHover] = useState<Hover | null>(null);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  if (days.length === 0) return null;

  const onMouseOver = (ev: MouseEvent<HTMLDivElement>) => {
    window.clearTimeout(timer.current);
    setHover(null);
    const cell = ev.target as HTMLElement;
    const day = cell.dataset.day;
    const row = cell.parentElement?.dataset.row;
    if (day === undefined || row === undefined) return;
    const next = { row: Number(row), day: Number(day), left: cell.offsetLeft, top: cell.offsetTop };
    timer.current = window.setTimeout(() => setHover(next), TIP_DELAY_MS);
  };
  const onMouseLeave = () => {
    window.clearTimeout(timer.current);
    setHover(null);
  };

  const hoverEmployee = hover ? employees[hover.row] : undefined;
  const hoverDay = hover ? days[hover.day] : undefined;

  // Палитра ячеек: обложка, светлая и тёмная.
  const palette = skin
    ? {
        weekendBg: '#E1DED7',
        emptyBg: '#FFFFFF',
        cellBorder: '#CFCCC4',
        monthSep: '#9A978F',
        monthLabel: '#1C1C1A',
        dayHeader: '#5C5A55',
        weekendHeader: '#5C5A55',
        nameColor: '#1C1C1A',
      }
    : isLight
    ? {
        weekendBg: '#dde3ec',
        emptyBg: '#eef2f7',
        cellBorder: 'rgba(195,203,217,0.5)',
        monthSep: '#c3cbd9',
        monthLabel: '#3f4860',
        dayHeader: '#5d6680',
        weekendHeader: '#4e5770',
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
  const monthGroups = [...new Set(days.map((d) => d.month))].map((m) => ({
    month: m,
    count: days.filter((d) => d.month === m).length,
  }));

  // Уникальные причины для легенды
  const uniqueReasons = new Map<string, string>();
  for (const a of absences) {
    if (!uniqueReasons.has(a.reason_label)) {
      uniqueReasons.set(a.reason_label, a.reason_color ?? DEFAULT_REASON_COLOR);
    }
  }

  return (
    <div style={{ overflowX: 'auto', marginBottom: 12 }}>
      {/* Заголовки месяцев */}
      <div style={{ display: 'flex', marginLeft: NAME_COL_WIDTH, marginBottom: 4 }}>
        {monthGroups.map((g, idx) => (
          <div
            key={`mh-${g.month}`}
            style={{
              width: g.count * (CELL + 1),
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
      <div
        data-grid
        className="absence-heatmap__grid"
        onMouseOver={onMouseOver}
        onMouseLeave={onMouseLeave}
        style={{
          display: 'inline-grid',
          gridTemplateColumns: `${NAME_COL_WIDTH}px repeat(${days.length}, ${CELL}px)`,
          gap: 1,
          '--ahm-empty-bg': palette.emptyBg,
          '--ahm-weekend-bg': palette.weekendBg,
          '--ahm-cell-border': palette.cellBorder,
          '--ahm-month-sep': palette.monthSep,
          '--ahm-name': palette.nameColor,
        } as CSSProperties}
      >
        <div />
        {days.map((d) => (
          <div
            key={`h-${d.iso}`}
            style={{
              fontSize: 9,
              textAlign: 'center',
              color: d.weekend ? palette.weekendHeader : palette.dayHeader,
              borderLeft: d.monthStart ? `1px solid ${palette.monthSep}` : 'none',
            }}
          >
            {d.label}
          </div>
        ))}
        <HeatmapRows employees={employees} days={days} cells={cells} />
        {hover && hoverEmployee && hoverDay && (
          <Tooltip
            key={`${hover.row}-${hover.day}`}
            open
            title={absenceCellTip(hoverEmployee.display_name, hoverDay, cells.get(hoverEmployee.id)?.[hover.day])}
          >
            <div className="absence-heatmap__anchor" style={{ left: hover.left, top: hover.top }} />
          </Tooltip>
        )}
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

export default memo(AbsenceHeatmap);
