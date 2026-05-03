import type { InitiativePertOut } from '../../api/resourcePlanning';
import { dateToLeft } from '../../utils/gantt';
import type { GanttTimeline } from '../../utils/gantt';

interface Props {
  pert: InitiativePertOut[];
  timeline: GanttTimeline;
  rowRefs: React.MutableRefObject<Map<string, HTMLElement>>;
}

export default function PertOverlay({ pert, timeline, rowRefs }: Props) {
  return (
    <svg
      style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        width: '100%',
        height: '100%',
      }}
    >
      {pert.map(p => {
        if (!p.p50_finish || !p.p90_finish) return null;
        const row = rowRefs.current.get(p.backlog_item_id);
        if (!row) return null;
        const top = row.offsetTop + row.offsetHeight / 2;
        const p50x = `${dateToLeft(p.p50_finish, timeline)}%`;
        const p90x = `${dateToLeft(p.p90_finish, timeline)}%`;
        return (
          <g key={p.backlog_item_id}>
            <line x1={p50x} x2={p50x} y1={top - 6} y2={top + 6} stroke="#00c9c8" strokeWidth={2} />
            <line x1={p90x} x2={p90x} y1={top - 6} y2={top + 6} stroke="#d4a017" strokeWidth={2} strokeDasharray="4 2" />
            <line x1={p50x} x2={p90x} y1={top} y2={top} stroke="#d4a017" strokeWidth={1} opacity={0.5} />
          </g>
        );
      })}
    </svg>
  );
}
