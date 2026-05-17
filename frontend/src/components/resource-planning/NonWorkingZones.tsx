import { useMemo } from 'react';
import type { GanttTimeline, TimelineScale, WorkdayTimeline } from '../../utils/gantt';
import type { ProductionCalendarDayResponse } from '../../types/api';

interface Props {
  timeline: GanttTimeline | WorkdayTimeline;
  calendar: ProductionCalendarDayResponse[];
  scale: TimelineScale;
  /** Если true — скрывать полосы в режимах week/month (визуальный мусор при крупном масштабе) */
  hideInWeekMonth?: boolean;
}

// Фоновые полосы выходных/праздников во всю высоту трека. Подложка под бары
// (zIndex: 0), не перехватывает события.
export default function NonWorkingZones({ timeline, calendar, scale, hideInWeekMonth }: Props) {
  const hidden = 'workdayIndex' in timeline || (!!hideInWeekMonth && (scale === 'week' || scale === 'month'));

  const stripes = useMemo(() => {
    if (hidden || 'workdayIndex' in timeline) return [];
    const out: Array<{ key: string; leftPct: number; widthPct: number; kind: 'weekend' | 'holiday' }> = [];
    const calMap = new Map(calendar.map(d => [d.date, d]));
    const cursor = new Date(timeline.startDate);
    for (let i = 0; i < timeline.totalDays; i++) {
      const iso = `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, '0')}-${String(cursor.getDate()).padStart(2, '0')}`;
      const dow = cursor.getDay(); // 0=Sun, 6=Sat
      const row = calMap.get(iso);
      let kind: 'weekend' | 'holiday' | null = null;
      if (row) {
        if (!row.is_workday) {
          kind = row.kind === 'holiday' || row.kind === 'preholiday' ? 'holiday' : 'weekend';
        }
      } else if (dow === 0 || dow === 6) {
        kind = 'weekend';
      }
      if (kind) {
        out.push({
          key: iso,
          leftPct: (i / timeline.totalDays) * 100,
          widthPct: (1 / timeline.totalDays) * 100,
          kind,
        });
      }
      cursor.setDate(cursor.getDate() + 1);
    }
    return out;
  }, [timeline, calendar, hidden]);

  if (hidden) return null;

  return (
    <>
      {stripes.map(s => (
        <div
          key={s.key}
          style={{
            position: 'absolute',
            left: `${s.leftPct}%`,
            width: `${s.widthPct}%`,
            top: 0,
            bottom: 0,
            background:
              s.kind === 'holiday'
                ? 'rgba(232, 134, 74, 0.10)'
                : 'rgba(120, 145, 180, 0.075)',
            zIndex: 0,
            pointerEvents: 'none',
          }}
        />
      ))}
    </>
  );
}
