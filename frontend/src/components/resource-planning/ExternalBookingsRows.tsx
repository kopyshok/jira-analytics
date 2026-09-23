import { useMemo, useState } from 'react';
import type { ExternalBookingOut } from '../../api/resourcePlanning';
import type { ProductionCalendarDayResponse } from '../../types/api';
import type { GanttTimeline, WorkdayTimeline } from '../../utils/gantt';
import { dateToLeft, datesToWidth, fmtLocalIso } from '../../utils/gantt';
import {
  bookingRuns,
  externalBookingLabel,
  groupExternalBookings,
  phaseCountLabel,
} from '../../utils/externalBookings';

const ROW_H = 28;
const BAR_H = 16;
// Серая штриховка: чужая работа, только просмотр.
const HATCH =
  'repeating-linear-gradient(45deg, rgba(160,170,190,0.55) 0 4px, rgba(160,170,190,0.18) 4px 8px)';
// Левая колонка перекрывает метку «сегодня» (z=20) при горизонтальном скролле —
// как у строк задач.
const STICKY_Z = 25;

interface Props {
  bookings: ExternalBookingOut[];
  timeline: GanttTimeline | WorkdayTimeline;
  calendar: ProductionCalendarDayResponse[];
  leftColWidth: number;
  trackWidthPx: number;
}

const ddmm = (iso: string) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;

/**
 * Блок «Привлечённые»: фазы привлечённых сотрудников в опорных планах других
 * команд. Только просмотр. Полосы — дни с часами, так что паузы внутри чужой
 * фазы видны как свободные окна.
 */
export default function ExternalBookingsRows({
  bookings,
  timeline,
  calendar,
  leftColWidth,
  trackWidthPx,
}: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const rows = useMemo(() => {
    const from = fmtLocalIso(timeline.startDate);
    const to = fmtLocalIso(timeline.endDate);
    const workday = new Map(calendar.map((c) => [c.date, c.is_workday]));
    const isWorkday = (iso: string) => {
      const known = workday.get(iso);
      if (known !== undefined) return known;
      const dow = new Date(iso + 'T00:00:00').getDay();
      return dow !== 0 && dow !== 6;
    };
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
        onClick={() => setCollapsed((v) => !v)}
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
          Привлечённые
        </span>
        <span style={{ fontSize: 11, color: 'var(--text-hint, #7a9ab8)' }}>
          {phaseCountLabel(rows.length)} в планах других команд · только просмотр
        </span>
      </button>
      {!collapsed && rows.map(({ b, runs }) => {
        const label = externalBookingLabel(b);
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
                    background: HATCH,
                    border: '1px solid rgba(160,170,190,0.5)',
                    zIndex: 2,
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
