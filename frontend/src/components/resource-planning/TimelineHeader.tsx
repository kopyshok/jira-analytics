import { useMemo } from 'react';
import type { GanttTimeline, TimelineScale } from '../../utils/gantt';
import { getDayLabels, getMonthLabels, getWeekLabels } from '../../utils/gantt';

interface Props {
  timeline: GanttTimeline;
  leftColWidth: number;
  scale?: TimelineScale;
  trackWidthPx?: number;
}

const MONTH_NAMES = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];

export default function TimelineHeader({ timeline, leftColWidth, scale = 'week', trackWidthPx }: Props) {
  const lower = useMemo(() => {
    if (scale === 'day') return getDayLabels(timeline);
    if (scale === 'month') return getMonthLabels(timeline);
    return getWeekLabels(timeline);
  }, [timeline, scale]);

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

  // При scale=month нижний ряд уже показывает месяцы — верхний скрываем,
  // вместо него рисуем годы
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
          {lower.map((w, i) => (
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
                color: '#4a6a90',
                borderRight: '1px solid #142a45',
                overflow: 'hidden',
                whiteSpace: 'nowrap',
              }}
            >
              {w.label}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
