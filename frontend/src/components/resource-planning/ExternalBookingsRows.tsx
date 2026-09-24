import { useMemo } from 'react';
import type { ExternalBookingOut } from '../../api/resourcePlanning';
import type { ProductionCalendarDayResponse } from '../../types/api';
import type { GanttTimeline, WorkdayTimeline } from '../../utils/gantt';
import { dateToLeft, datesToWidth, fmtLocalIso } from '../../utils/gantt';
import {
  OTHER_TEAM_HATCH,
  bookingRuns,
  externalBookingLabel,
  groupExternalBookings,
  phaseCountLabel,
  workdayChecker,
} from '../../utils/externalBookings';

const ROW_H = 28;
const BAR_H = 16;
// Левая колонка перекрывает метку «сегодня» (z=20) при горизонтальном скролле —
// как у строк задач.
const STICKY_Z = 25;
const OVERLAP_HINT = 'пересекается с вашим планом — техкоманда получит конфликт';

interface Props {
  bookings: ExternalBookingOut[];
  timeline: GanttTimeline | WorkdayTimeline;
  calendar: ProductionCalendarDayResponse[];
  leftColWidth: number;
  trackWidthPx: number;
  /** Заголовок блока. */
  title: string;
  /** Подпись строки; по умолчанию «KEY · Фаза · Имя». */
  labelOf?: (b: ExternalBookingOut) => string;
  /** Красная отметка в днях, где этот план тоже занял человека. */
  showOverlap?: boolean;
  /** Блок свёрнут. Состояние у диаграммы: при сворачивании строки ниже
   *  сдвигаются, и стрелки связей надо перерисовать. */
  collapsed: boolean;
  onToggle: () => void;
}

const ddmm = (iso: string) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;

/**
 * Брони людей плана в опорных планах других команд: блоки «Привлечённые»
 * и «Наши люди в других командах». Только просмотр. Полосы — дни с часами,
 * так что паузы внутри чужой фазы видны как свободные окна.
 */
export default function ExternalBookingsRows({
  bookings,
  timeline,
  calendar,
  leftColWidth,
  trackWidthPx,
  title,
  labelOf = externalBookingLabel,
  showOverlap = false,
  collapsed,
  onToggle,
}: Props) {
  const rows = useMemo(() => {
    const from = fmtLocalIso(timeline.startDate);
    const to = fmtLocalIso(timeline.endDate);
    const isWorkday = workdayChecker(calendar);
    return groupExternalBookings(bookings)
      .flatMap((g) => g.rows)
      .map((b) => ({ b, runs: bookingRuns(b.daily_hours, from, to, isWorkday) }))
      .filter((r) => r.runs.length > 0);
  }, [bookings, timeline, calendar]);

  if (rows.length === 0) return null;

  return (
    <div style={{ borderBottom: '2px solid #066770' }}>
      {/* Шапка сворачивает блок — как секции групп команды. */}
      <button
        type="button"
        aria-expanded={!collapsed}
        onClick={onToggle}
        style={{
          position: 'sticky',
          left: 0,
          zIndex: STICKY_Z,
          width: leftColWidth,
          boxSizing: 'border-box',
          display: 'flex',
          alignItems: 'baseline',
          gap: 10,
          padding: '6px 14px',
          background: '#0a1628',
          border: 0,
          borderBottom: '1px solid #1e3a5f',
          cursor: 'pointer',
          userSelect: 'none',
          textAlign: 'left',
          font: 'inherit',
        }}
      >
        <span aria-hidden="true" style={{ fontSize: 11, color: 'var(--text-muted, #7a9ab8)' }}>
          {collapsed ? '▶' : '▼'}
        </span>
        <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary, #e6f0f7)' }}>
          {title}
        </span>
        <span style={{ fontSize: 11, color: 'var(--text-hint, #7a9ab8)' }}>
          {phaseCountLabel(rows.length)} в планах других команд · только просмотр
        </span>
      </button>
      {!collapsed && rows.map(({ b, runs }) => {
        const label = labelOf(b);
        const meta = b.provisional ? `${b.team} · предварительно` : b.team;
        return (
          <div
            key={b.assignment_id}
            style={{ display: 'flex', height: ROW_H, borderBottom: '1px solid #0e2540' }}
          >
            <div
              title={`${label} — ${meta}`}
              style={{
                width: leftColWidth,
                boxSizing: 'border-box',
                flexShrink: 0,
                position: 'sticky',
                left: 0,
                zIndex: STICKY_Z,
                background: '#0a1628',
                borderRight: '1px solid #1e3a5f',
                display: 'grid',
                gridTemplateColumns: 'minmax(0, 1fr) 160px',
                columnGap: 8,
                alignItems: 'center',
                padding: '0 12px',
                fontSize: 12,
                whiteSpace: 'nowrap',
              }}
            >
              <span style={{ color: '#9ab3cc', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {label}
              </span>
              {/* «предварительно» — отдельной строкой: длинное название команды его не съест. */}
              <span style={{ display: 'flex', flexDirection: 'column', minWidth: 0, fontSize: 11, lineHeight: 1.15 }}>
                <span style={{ color: '#7a9ab8', overflow: 'hidden', textOverflow: 'ellipsis' }}>{b.team}</span>
                {b.provisional && <span style={{ fontSize: 10, color: '#e0a84a' }}>предварительно</span>}
              </span>
            </div>
            <div style={{ position: 'relative', width: trackWidthPx, flex: '0 0 auto' }}>
              {runs.map((r) => (
                <div
                  key={r.start}
                  title={`${label} — ${meta}: ${ddmm(r.start)}–${ddmm(r.end)}, ${Math.round(r.hours)} ч. Только просмотр`}
                  style={{
                    position: 'absolute',
                    left: `${dateToLeft(r.start, timeline)}%`,
                    width: `${datesToWidth(r.start, r.end, timeline)}%`,
                    top: (ROW_H - BAR_H) / 2,
                    height: BAR_H,
                    boxSizing: 'border-box',
                    borderRadius: 3,
                    background: OTHER_TEAM_HATCH,
                    border: '1px solid rgba(160,170,190,0.5)',
                    zIndex: 2,
                  }}
                />
              ))}
              {showOverlap && b.overlap_days.map((d) => (
                <div
                  key={`overlap-${d}`}
                  title={`${ddmm(d)}: ${OVERLAP_HINT}`}
                  style={{
                    position: 'absolute',
                    left: `${dateToLeft(d, timeline)}%`,
                    width: `${datesToWidth(d, d, timeline)}%`,
                    top: (ROW_H - BAR_H) / 2 - 2,
                    height: BAR_H + 4,
                    boxSizing: 'border-box',
                    border: '2px solid #ef4444',
                    borderRadius: 3,
                    zIndex: 3,
                  }}
                />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
