import { useMemo } from 'react';
import type { GanttTimeline } from '../../utils/gantt';
import { getWeekLabels } from '../../utils/gantt';

interface Props {
  timeline: GanttTimeline;
  leftColWidth: number;
}

const MONTH_NAMES = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];

export default function TimelineHeader({ timeline, leftColWidth }: Props) {
  const weeks = useMemo(() => getWeekLabels(timeline), [timeline]);

  const months = useMemo(() => {
    const map = new Map<string, { label: string; leftPct: number; rightPct: number }>();
    weeks.forEach(w => {
      const approxDate = new Date(timeline.startDate);
      approxDate.setDate(approxDate.getDate() + Math.round(w.leftPct / 100 * timeline.totalDays));
      const key = `${approxDate.getFullYear()}-${approxDate.getMonth()}`;
      const label = `${MONTH_NAMES[approxDate.getMonth()]} ${approxDate.getFullYear()}`;
      if (!map.has(key)) map.set(key, { label, leftPct: w.leftPct, rightPct: w.leftPct + w.widthPct });
      else map.get(key)!.rightPct = w.leftPct + w.widthPct;
    });
    return [...map.values()];
  }, [weeks, timeline]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid #1e3a5f' }}>
      <div style={{ display: 'flex', height: 28, background: '#091829' }}>
        <div style={{ width: leftColWidth, flexShrink: 0, borderRight: '1px solid #1e3a5f' }} />
        <div style={{ flex: 1, position: 'relative' }}>
          {months.map(m => (
            <div
              key={m.label}
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
        <div style={{ flex: 1, position: 'relative' }}>
          {weeks.map(w => (
            <div
              key={w.label}
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
