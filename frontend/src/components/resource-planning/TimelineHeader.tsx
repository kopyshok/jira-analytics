import { useMemo } from 'react';
import type { GanttTimeline, TimelineScale } from '../../utils/gantt';
import { getDayLabels, getMonthLabels, getWeekLabels } from '../../utils/gantt';
import type { ProductionCalendarDayResponse } from '../../types/api';

interface Props {
  timeline: GanttTimeline;
  leftColWidth: number;
  scale?: TimelineScale;
  trackWidthPx?: number;
  calendar?: ProductionCalendarDayResponse[];
}

const MONTH_NAMES = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];

interface CellTint {
  bg: string | null;
  fg: string | null;
}

function tintForDow(dow: number): CellTint {
  if (dow === 0 || dow === 6) {
    return { bg: 'rgba(120, 145, 180, 0.10)', fg: '#7a99c4' };
  }
  return { bg: null, fg: null };
}

function tintForCalendar(row: ProductionCalendarDayResponse, dow: number): CellTint {
  if (!row.is_workday) {
    if (row.kind === 'holiday' || row.kind === 'preholiday') {
      return { bg: 'rgba(232, 134, 74, 0.18)', fg: '#f0a075' };
    }
    return { bg: 'rgba(120, 145, 180, 0.14)', fg: '#7a99c4' };
  }
  return tintForDow(dow);
}

export default function TimelineHeader({
  timeline,
  leftColWidth,
  scale = 'week',
  trackWidthPx,
  calendar,
}: Props) {
  const calMap = useMemo(() => {
    const m = new Map<string, ProductionCalendarDayResponse>();
    (calendar ?? []).forEach(d => m.set(d.date, d));
    return m;
  }, [calendar]);

  const days = useMemo(() => (scale === 'day' ? getDayLabels(timeline) : []), [timeline, scale]);

  const lower = useMemo(() => {
    if (scale === 'day') return days.map(d => ({ label: d.label, leftPct: d.leftPct, widthPct: d.widthPct }));
    if (scale === 'month') return getMonthLabels(timeline);
    return getWeekLabels(timeline);
  }, [timeline, scale, days]);

  const months = useMemo(() => {
    const map = new Map<string, { label: string; leftPct: number; rightPct: number }>();
    lower.forEach(w => {
      const approxDate = new Date(timeline.startDate);
      approxDate.setDate(approxDate.getDate() + Math.round(w.leftPct / 100 * timeline.totalDays));
      const key = `${approxDate.getFullYear()}-${approxDate.getMonth()}`;
      const label = `${MONTH_NAMES[approxDate.getMonth()]} ${approxDate.getFullYear()}`;
      if (!map.has(key)) map.set(key, { label, leftPct: w.leftPct, rightPct: w.leftPct + w.widthPct });
      else map.get(key)!.rightPct = w.leftPct + w.widthPct;
    });
    return [...map.values()];
  }, [lower, timeline]);

  const years = useMemo(() => {
    if (scale !== 'month') return [];
    const map = new Map<number, { label: string; leftPct: number; rightPct: number }>();
    lower.forEach(w => {
      const approxDate = new Date(timeline.startDate);
      approxDate.setDate(approxDate.getDate() + Math.round(w.leftPct / 100 * timeline.totalDays));
      const y = approxDate.getFullYear();
      if (!map.has(y)) map.set(y, { label: String(y), leftPct: w.leftPct, rightPct: w.leftPct + w.widthPct });
      else map.get(y)!.rightPct = w.leftPct + w.widthPct;
    });
    return [...map.values()];
  }, [lower, timeline, scale]);

  const upperRow = scale === 'month' ? years : months;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid #1e3a5f' }}>
      <div style={{ display: 'flex', height: 28, background: '#091829' }}>
        <div style={{ width: leftColWidth, flexShrink: 0, borderRight: '1px solid #1e3a5f' }} />
        <div style={{ width: trackWidthPx ?? undefined, flex: trackWidthPx ? '0 0 auto' : 1, position: 'relative' }}>
          {upperRow.map((m, i) => (
            <div
              key={`${m.label}-${i}`}
              style={{
                position: 'absolute',
                left: `${m.leftPct}%`,
                width: `${m.rightPct - m.leftPct}%`,
                height: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 11,
                fontWeight: 700,
                color: '#5a7aaa',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                borderRight: '1px solid #1e3a5f',
              }}
            >
              {m.label}
            </div>
          ))}
        </div>
      </div>
      <div style={{ display: 'flex', height: 24, background: '#0a1e35' }}>
        <div style={{ width: leftColWidth, flexShrink: 0, borderRight: '1px solid #1e3a5f' }} />
        <div style={{ width: trackWidthPx ?? undefined, flex: trackWidthPx ? '0 0 auto' : 1, position: 'relative' }}>
          {lower.map((w, i) => {
            let tint: CellTint = { bg: null, fg: null };
            if (scale === 'day' && days[i]) {
              const dInfo = days[i];
              const cal = calMap.get(dInfo.iso);
              tint = cal ? tintForCalendar(cal, dInfo.dow) : tintForDow(dInfo.dow);
            }
            return (
              <div
                key={`${w.label}-${i}-${w.leftPct}`}
                style={{
                  position: 'absolute',
                  left: `${w.leftPct}%`,
                  width: `${w.widthPct}%`,
                  height: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 10,
                  color: tint.fg ?? '#4a6a90',
                  background: tint.bg ?? 'transparent',
                  borderRight: '1px solid #142a45',
                  overflow: 'hidden',
                  whiteSpace: 'nowrap',
                }}
              >
                {w.label}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
