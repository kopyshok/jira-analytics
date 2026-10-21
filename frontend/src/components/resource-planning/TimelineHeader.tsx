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
  /** Плотный режим: шапка ниже, месяцы — подписью слева без года, недели — датами понедельников. */
  compact?: boolean;
  /** Подпись левой колонки в плотном режиме — по раскладке строк диаграммы. */
  caption?: string;
}

const MONTH_NAMES = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];

interface CellTint {
  bg: string | null;
  fg: string | null;
}

// Цвета — через CSS-переменные скина; без скина берётся прежнее значение.
function tintForDow(dow: number): CellTint {
  if (dow === 0 || dow === 6) {
    return { bg: 'var(--rp-th-weekend-bg, rgba(120, 145, 180, 0.10))', fg: 'var(--rp-th-weekend-fg, #7a99c4)' };
  }
  return { bg: null, fg: null };
}

function tintForCalendar(row: ProductionCalendarDayResponse, dow: number): CellTint {
  if (!row.is_workday) {
    if (row.kind === 'holiday' || row.kind === 'preholiday') {
      return { bg: 'var(--rp-th-holiday-bg, rgba(232, 134, 74, 0.18))', fg: 'var(--rp-th-holiday-fg, #f0a075)' };
    }
    return { bg: 'var(--rp-th-off-bg, rgba(120, 145, 180, 0.14))', fg: 'var(--rp-th-weekend-fg, #7a99c4)' };
  }
  return tintForDow(dow);
}

export default function TimelineHeader({
  timeline,
  leftColWidth,
  scale = 'week',
  trackWidthPx,
  calendar,
  compact = false,
  caption = 'Инициатива · фаза · исполнитель',
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
    return getWeekLabels(timeline, compact ? 'monday' : 'num');
  }, [timeline, scale, days, compact]);

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
    <div className={compact ? 'rp-th rp-th-compact' : 'rp-th'} style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid var(--rp-border, #1e3a5f)' }}>
      <div style={{ display: 'flex', height: compact ? 20 : 28, background: 'var(--rp-th-bg, #091829)' }}>
        <div style={{ width: leftColWidth, boxSizing: 'border-box', flexShrink: 0, borderRight: '1px solid var(--rp-border, #1e3a5f)', position: 'sticky', left: 0, zIndex: 31, background: 'var(--rp-th-bg, #091829)' }} />
        <div style={{ width: trackWidthPx ?? undefined, flex: trackWidthPx ? '0 0 auto' : 1, position: 'relative' }}>
          {upperRow.map((m, i) => (
            <div
              key={`${m.label}-${i}`}
              className="rp-th-upper"
              style={{
                position: 'absolute',
                left: `${m.leftPct}%`,
                width: `${m.rightPct - m.leftPct}%`,
                height: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: compact ? 'flex-start' : 'center',
                paddingLeft: compact ? 6 : undefined,
                boxSizing: compact ? 'border-box' : undefined,
                fontSize: 11,
                fontWeight: compact ? 600 : 700,
                color: 'var(--rp-th-month, #5a7aaa)',
                textTransform: compact ? 'none' : 'uppercase',
                letterSpacing: compact ? 0 : '0.06em',
                borderRight: compact ? undefined : '1px solid var(--rp-border, #1e3a5f)',
                borderLeft: compact ? '1px solid var(--rp-th-month-line, #1e3a5f)' : undefined,
              }}
            >
              {m.label}
            </div>
          ))}
        </div>
      </div>
      <div style={{ display: 'flex', height: 24, background: 'var(--rp-th-bg-2, #0a1e35)' }}>
        <div className="rp-th-corner" style={{ width: leftColWidth, boxSizing: 'border-box', flexShrink: 0, borderRight: '1px solid var(--rp-border, #1e3a5f)', position: 'sticky', left: 0, zIndex: 31, background: 'var(--rp-th-bg-2, #0a1e35)' }}>
          {compact && <span className="rp-th-caption">{caption}</span>}
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
                style={{
                  position: 'absolute',
                  left: `${w.leftPct}%`,
                  width: `${w.widthPct}%`,
                  height: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: compact ? 10.5 : 10,
                  color: tint.fg ?? 'var(--rp-th-week, #4a6a90)',
                  background: tint.bg ?? 'transparent',
                  borderRight: '1px solid var(--rp-th-week-line, #142a45)',
                  overflow: 'hidden',
                  whiteSpace: 'nowrap',
                }}
              >
                {w.label}
                {scale === 'week' && weeksWithHoliday.has(w.label) && (
                  <span
                    title="В неделе есть праздничный день"
                    style={{ position: 'absolute', bottom: 1, right: 4, color: 'var(--rp-th-holiday-fg, #f0a075)', fontSize: 9, lineHeight: 1 }}
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
