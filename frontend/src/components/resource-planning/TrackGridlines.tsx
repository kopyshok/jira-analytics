import { useMemo } from 'react';
import type { GanttTimeline, TimelineScale, WorkdayTimeline } from '../../utils/gantt';

interface Props {
  timeline: GanttTimeline | WorkdayTimeline;
  scale: TimelineScale;
}

// Вертикальные разделители дней/недель/месяцев в треке. Под барами, над
// NonWorkingZones. Не перехватывает события.
export default function TrackGridlines({ timeline, scale }: Props) {
  const lines = useMemo(() => {
    const out: Array<{ key: string; leftPct: number; kind: 'day' | 'week' | 'month' }> = [];
    const isWorkday = 'workdayIndex' in timeline;

    if (isWorkday) {
      // Workday mode: gridlines only between consecutive workdays
      const { workdayDates, totalDays } = timeline as import('../../utils/gantt').WorkdayTimeline;
      for (let i = 1; i < workdayDates.length; i++) {
        const leftPct = (i / totalDays) * 100;
        const iso = workdayDates[i];
        const d = new Date(iso + 'T00:00:00');
        const isMonthStart = d.getDate() === 1;
        const isWeekStart = d.getDay() === 1;
        const key = `wd-${iso}`;
        if (isMonthStart) {
          out.push({ key, leftPct, kind: 'month' });
        } else if (isWeekStart) {
          out.push({ key, leftPct, kind: 'week' });
        } else {
          out.push({ key, leftPct, kind: 'day' });
        }
      }
      return out;
    }

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
          style.borderLeft = '1px solid rgba(160, 200, 240, 0.20)';
        } else {
          style.borderLeft = '1px dotted rgba(160, 200, 240, 0.05)';
        }
        return <div key={l.key} style={style} />;
      })}
    </>
  );
}
