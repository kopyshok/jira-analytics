import { useMemo } from 'react';
import type { GanttTimeline, TimelineScale, WorkdayTimeline } from '../../utils/gantt';
import { getDayLabels, getMonthLabels, getWeekLabels } from '../../utils/gantt';
import type { ProductionCalendarDayResponse } from '../../types/api';

/** Дата, к которой относится позиция leftPct на timeline.
 *  Для calendar-таймлайна: startDate + leftPct/100*totalDays calendar-days.
 *  Для workday-таймлайна: workdayDates[round(leftPct/100*totalDays)] — иначе
 *  смешение workday-процента с calendar-сдвигом даёт неверный месяц.
 */
function dateAtLeftPct(tl: GanttTimeline | WorkdayTimeline, leftPct: number): Date {
  if ('workdayIndex' in tl) {
    const idx = Math.min(
      Math.max(0, Math.round(leftPct / 100 * tl.totalDays)),
      tl.workdayDates.length - 1,
    );
    const iso = tl.workdayDates[idx];
    if (iso) return new Date(iso + 'T00:00:00');
  }
  const d = new Date(tl.startDate);
  d.setDate(d.getDate() + Math.round(leftPct / 100 * tl.totalDays));
  return d;
}

interface Props {
  timeline: GanttTimeline | WorkdayTimeline;
  leftColWidth: number;
  scale?: TimelineScale;
  trackWidthPx?: number;
  calendar?: ProductionCalendarDayResponse[];
  /** Компактные подписи: месяцы без года, недели — датой понедельника, подпись левой колонки. */
  compact?: boolean;
  /** Позиция «сегодня» (% шкалы) — метка в строке месяцев. */
  todayLeftPct?: number;
}

const MONTH_NAMES = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];

interface CellTint {
  bg: string | null;
  fg: string | null;
}

function tintForDow(dow: number): CellTint {
  if (dow === 0 || dow === 6) {
    return { bg: 'var(--rp-weekend-bg, rgba(120, 145, 180, 0.10))', fg: 'var(--rp-weekend-fg, #7a99c4)' };
  }
  return { bg: null, fg: null };
}

function tintForCalendar(row: ProductionCalendarDayResponse, dow: number): CellTint {
  if (!row.is_workday) {
    if (row.kind === 'holiday' || row.kind === 'preholiday') {
      return { bg: 'var(--rp-holiday-bg, rgba(232, 134, 74, 0.18))', fg: 'var(--rp-holiday-fg, #f0a075)' };
    }
    return { bg: 'var(--rp-dayoff-bg, rgba(120, 145, 180, 0.14))', fg: 'var(--rp-weekend-fg, #7a99c4)' };
  }
  return tintForDow(dow);
}

const ddmm = (d: Date) => `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}`;

export default function TimelineHeader({
  timeline,
  leftColWidth,
  scale = 'week',
  trackWidthPx,
  calendar,
  compact = false,
  todayLeftPct,
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
      const approxDate = dateAtLeftPct(timeline, w.leftPct);
      const key = `${approxDate.getFullYear()}-${approxDate.getMonth()}`;
      const label = compact
        ? MONTH_NAMES[approxDate.getMonth()]
        : `${MONTH_NAMES[approxDate.getMonth()]} ${approxDate.getFullYear()}`;
      if (!map.has(key)) map.set(key, { label, leftPct: w.leftPct, rightPct: w.leftPct + w.widthPct });
      else map.get(key)!.rightPct = w.leftPct + w.widthPct;
    });
    return [...map.values()];
  }, [lower, timeline, compact]);

  const years = useMemo(() => {
    if (scale !== 'month') return [];
    const map = new Map<number, { label: string; leftPct: number; rightPct: number }>();
    lower.forEach(w => {
      const approxDate = dateAtLeftPct(timeline, w.leftPct);
      const y = approxDate.getFullYear();
      if (!map.has(y)) map.set(y, { label: String(y), leftPct: w.leftPct, rightPct: w.leftPct + w.widthPct });
      else map.get(y)!.rightPct = w.leftPct + w.widthPct;
    });
    return [...map.values()];
  }, [lower, timeline, scale]);

  const upperRow = scale === 'month' ? years : months;
  const fullWeekPct = Math.max(...lower.map(w => w.widthPct), 0);

  const weeksWithHoliday = useMemo(() => {
    if (scale !== 'week') return new Set<string>();
    const set = new Set<string>();
    for (const w of lower) {
      const weekStart = dateAtLeftPct(timeline, w.leftPct);
      const weekEnd = new Date(weekStart);
      weekEnd.setDate(weekEnd.getDate() + 6);
      for (const cal of calendar ?? []) {
        const d = new Date(cal.date + 'T00:00:00');
        if (d >= weekStart && d <= weekEnd && !cal.is_workday && (cal.kind === 'holiday' || cal.kind === 'preholiday')) {
          set.add(w.label);
          break;
        }
      }
    }
    return set;
  }, [timeline, scale, calendar, lower]);

  return (
    <div className="rp-th" style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid var(--rp-th-line, #1e3a5f)' }}>
      <div className="rp-th-upper" style={{ display: 'flex', height: 'var(--rp-th-h1, 28px)', background: 'var(--rp-head-bg, #091829)' }}>
        <div style={{ width: leftColWidth, boxSizing: 'border-box', flexShrink: 0, borderRight: '1px solid var(--rp-line, #1e3a5f)', position: 'sticky', left: 0, zIndex: 31, background: 'var(--rp-head-bg, #091829)' }} />
        <div style={{ width: trackWidthPx ?? undefined, flex: trackWidthPx ? '0 0 auto' : 1, position: 'relative' }}>
          {upperRow.map((m, i) => (
            <div
              key={`${m.label}-${i}`}
              className="rp-th-month"
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
                color: 'var(--rp-th-fg, #5a7aaa)',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
                borderRight: '1px solid var(--rp-line, #1e3a5f)',
              }}
            >
              {m.label}
            </div>
          ))}
          {todayLeftPct !== undefined && todayLeftPct >= 0 && todayLeftPct <= 100 && (
            <span className="rp-th-today" style={{ position: 'absolute', left: `${todayLeftPct}%` }}>
              сегодня
            </span>
          )}
        </div>
      </div>
      <div className="rp-th-lower" style={{ display: 'flex', height: 'var(--rp-th-h2, 24px)', background: 'var(--rp-head-bg-2, #0a1e35)' }}>
        <div className="rp-th-corner" style={{ width: leftColWidth, boxSizing: 'border-box', flexShrink: 0, borderRight: '1px solid var(--rp-line, #1e3a5f)', position: 'sticky', left: 0, zIndex: 31, background: 'var(--rp-head-bg-2, #0a1e35)' }}>
          {compact && 'Инициатива / фаза'}
        </div>
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
                className="rp-th-week"
                style={{
                  position: 'absolute',
                  left: `${w.leftPct}%`,
                  width: `${w.widthPct}%`,
                  height: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 10,
                  color: tint.fg ?? 'var(--rp-th-fg-2, #4a6a90)',
                  background: tint.bg ?? 'transparent',
                  borderRight: '1px solid var(--rp-line-week, #142a45)',
                  overflow: 'hidden',
                  whiteSpace: 'nowrap',
                }}
              >
                {compact && scale === 'week'
                  // Неполная неделя на краю квартала узкая — дата в неё не влезает.
                  ? (w.widthPct >= fullWeekPct * 0.7 ? ddmm(dateAtLeftPct(timeline, w.leftPct)) : '')
                  : w.label}
                {scale === 'week' && weeksWithHoliday.has(w.label) && (
                  <span
                    title="В неделе есть праздничный день"
                    style={{ position: 'absolute', bottom: 1, right: 4, color: 'var(--rp-holiday-fg, #f0a075)', fontSize: 9, lineHeight: 1 }}
                  >
                    ●
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
