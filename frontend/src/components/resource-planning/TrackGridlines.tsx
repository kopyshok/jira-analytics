import { useMemo } from 'react';
import type { GanttTimeline, TimelineScale } from '../../utils/gantt';

interface Props {
  timeline: GanttTimeline;
  scale: TimelineScale;
}

// Вертикальные разделители дней/недель/месяцев в треке. Под барами, над
// NonWorkingZones. Не перехватывает события.
export default function TrackGridlines({ timeline, scale }: Props) {
  const lines = useMemo(() => {
    const out: Array<{ key: string; leftPct: number; kind: 'day' | 'week' | 'month' }> = [];
    const cursor = new Date(timeline.startDate);
    for (let i = 1; i < timeline.totalDays; i++) {
      cursor.setDate(cursor.getDate() + 1);
      const isWeekStart = cursor.getDay() === 1; // Mon
      const isMonthStart = cursor.getDate() === 1;
      const leftPct = (i / timeline.totalDays) * 100;
      const iso = `${cursor.getFullYear()}-${cursor.getMonth() + 1}-${cursor.getDate()}`;
      if (isMonthStart) {
        out.push({ key: `m-${iso}`, leftPct, kind: 'month' });
      } else if (isWeekStart) {
        if (scale !== 'month') out.push({ key: `w-${iso}`, leftPct, kind: 'week' });
      } else if (scale === 'day') {
        out.push({ key: `d-${iso}`, leftPct, kind: 'day' });
      }
    }
    return out;
  }, [timeline, scale]);

  return (
    <>
      {lines.map(l => {
        const style: React.CSSProperties = {
          position: 'absolute',
          left: `${l.leftPct}%`,
          top: 0,
          bottom: 0,
          pointerEvents: 'none',
          zIndex: 1,
        };
        if (l.kind === 'month') {
          style.borderLeft = '1px solid rgba(160, 200, 240, 0.12)';
        } else if (l.kind === 'week') {
          style.borderLeft = '1px dashed rgba(160, 200, 240, 0.08)';
        } else {
          style.borderLeft = '1px dotted rgba(160, 200, 240, 0.05)';
        }
        return <div key={l.key} style={style} />;
      })}
    </>
  );
}
