import type { ScheduledBlock } from '../../api/resourcePlanning';
import type { GanttTimeline } from '../../utils/gantt';
import { dateToLeft, datesToWidth } from '../../utils/gantt';

interface Props {
  blocks: ScheduledBlock[];
  timeline: GanttTimeline;
}

export default function BlockedZones({ blocks, timeline }: Props) {
  return (
    <>
      {blocks.map(b => {
        const left = dateToLeft(b.start_date, timeline);
        const width = datesToWidth(b.start_date, b.end_date, timeline);
        return (
          <div
            key={b.id}
            title={b.reason}
            style={{
              position: 'absolute',
              left: `${left}%`,
              width: `${width}%`,
              top: 0,
              bottom: 0,
              background: 'repeating-linear-gradient(45deg, rgba(100,120,150,0.08), rgba(100,120,150,0.08) 4px, transparent 4px, transparent 10px)',
              borderLeft: '1px dashed rgba(100,150,200,0.3)',
              borderRight: '1px dashed rgba(100,150,200,0.3)',
              zIndex: 1,
              pointerEvents: 'none',
            }}
          >
            <span style={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%) rotate(-90deg)',
              fontSize: 9,
              color: 'rgba(150,180,220,0.5)',
              whiteSpace: 'nowrap',
              letterSpacing: '0.05em',
            }}>
              {b.reason}
            </span>
          </div>
        );
      })}
    </>
  );
}
