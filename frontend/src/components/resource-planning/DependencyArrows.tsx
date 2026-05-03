import { useEffect, useRef } from 'react';
import type { AssignmentOut } from '../../api/resourcePlanning';

interface Props {
  assignments: AssignmentOut[];
  rowRefs: React.MutableRefObject<Map<string, HTMLElement>>;
  containerRef: React.RefObject<HTMLDivElement>;
}

export default function DependencyArrows({ assignments, rowRefs, containerRef }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const svg = svgRef.current;
    const container = containerRef.current;
    if (!svg || !container) return;

    svg.innerHTML = '';
    const cRect = container.getBoundingClientRect();

    const PHASE_ORDER = ['analyst', 'dev', 'qa', 'opo'];
    const byItem = new Map<string, AssignmentOut[]>();
    for (const a of assignments) {
      if (!byItem.has(a.backlog_item_id)) byItem.set(a.backlog_item_id, []);
      byItem.get(a.backlog_item_id)!.push(a);
    }

    for (const [, itemAssignments] of byItem) {
      for (let i = 0; i < PHASE_ORDER.length - 1; i++) {
        const fromPhase = PHASE_ORDER[i];
        const toPhase = PHASE_ORDER[i + 1];
        const fromCandidates = itemAssignments.filter(a => a.phase === fromPhase);
        const maxPart = Math.max(...fromCandidates.map(x => x.part_number), 0);
        const from = fromCandidates.find(a => a.part_number === maxPart);
        const to = itemAssignments.find(a => a.phase === toPhase && a.part_number === 1);
        if (!from || !to) continue;

        const fromEl = rowRefs.current.get(`${from.backlog_item_id}-${from.phase}-${from.part_number}`);
        const toEl = rowRefs.current.get(`${to.backlog_item_id}-${to.phase}-${to.part_number}`);
        if (!fromEl || !toEl) continue;

        const fRect = fromEl.getBoundingClientRect();
        const tRect = toEl.getBoundingClientRect();
        const x1 = fRect.right - cRect.left;
        const y1 = fRect.top + fRect.height / 2 - cRect.top;
        const x2 = tRect.left - cRect.left;
        const y2 = tRect.top + tRect.height / 2 - cRect.top;

        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        const cx = (x1 + x2) / 2;
        path.setAttribute('d', `M${x1},${y1} C${cx},${y1} ${cx},${y2} ${x2},${y2}`);
        path.setAttribute('stroke', 'rgba(180,200,240,0.35)');
        path.setAttribute('stroke-width', '1.5');
        path.setAttribute('fill', 'none');
        path.setAttribute('marker-end', 'url(#rp-arrowhead)');
        svg.appendChild(path);
      }
    }
  });

  return (
    <svg
      ref={svgRef}
      style={{
        position: 'absolute',
        top: 0, left: 0,
        width: '100%', height: '100%',
        pointerEvents: 'none',
        overflow: 'visible',
        zIndex: 10,
      }}
    >
      <defs>
        <marker id="rp-arrowhead" markerWidth="6" markerHeight="4" refX="6" refY="2" orient="auto">
          <polygon points="0 0, 6 2, 0 4" fill="rgba(180,200,240,0.5)" />
        </marker>
      </defs>
    </svg>
  );
}
