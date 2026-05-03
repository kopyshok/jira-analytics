import { useEffect, useRef } from 'react';
import type { AssignmentOut } from '../../api/resourcePlanning';

interface Props {
  assignments: AssignmentOut[];
  rowRefs: React.MutableRefObject<Map<string, HTMLElement>>;
  containerRef: React.RefObject<HTMLDivElement>;
  showRelayArrows?: boolean;
}

export default function DependencyArrows({
  assignments,
  rowRefs,
  containerRef,
  showRelayArrows = true,
}: Props) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const svg = svgRef.current;
    const container = containerRef.current;
    if (!svg || !container) return;

    svg.innerHTML = '';

    // Re-inject defs after clearing innerHTML
    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');

    const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
    marker.setAttribute('id', 'rp-arrowhead');
    marker.setAttribute('markerWidth', '6');
    marker.setAttribute('markerHeight', '4');
    marker.setAttribute('refX', '6');
    marker.setAttribute('refY', '2');
    marker.setAttribute('orient', 'auto');
    const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    poly.setAttribute('points', '0 0, 6 2, 0 4');
    poly.setAttribute('fill', 'rgba(180,200,240,0.5)');
    marker.appendChild(poly);
    defs.appendChild(marker);

    const relayMarker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
    relayMarker.setAttribute('id', 'rp-relay-arrowhead');
    relayMarker.setAttribute('markerWidth', '6');
    relayMarker.setAttribute('markerHeight', '4');
    relayMarker.setAttribute('refX', '6');
    relayMarker.setAttribute('refY', '2');
    relayMarker.setAttribute('orient', 'auto');
    const relayPoly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    relayPoly.setAttribute('points', '0 0, 6 2, 0 4');
    relayPoly.setAttribute('fill', 'rgba(0,201,200,0.7)');
    relayMarker.appendChild(relayPoly);
    defs.appendChild(relayMarker);

    svg.appendChild(defs);

    const cRect = container.getBoundingClientRect();

    const svgEl: SVGSVGElement = svg;
    function drawArrow(
      x1: number, y1: number, x2: number, y2: number,
      color: string, width: string, dashArray: string, markerId: string,
    ) {
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      const cx = (x1 + x2) / 2;
      path.setAttribute('d', `M${x1},${y1} C${cx},${y1} ${cx},${y2} ${x2},${y2}`);
      path.setAttribute('stroke', color);
      path.setAttribute('stroke-width', width);
      path.setAttribute('fill', 'none');
      if (dashArray) path.setAttribute('stroke-dasharray', dashArray);
      path.setAttribute('marker-end', `url(#${markerId})`);
      svgEl.appendChild(path);
    }

    // Intra-initiative arrows (phase → next phase, same item)
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
        drawArrow(
          fRect.right - cRect.left,
          fRect.top + fRect.height / 2 - cRect.top,
          tRect.left - cRect.left,
          tRect.top + tRect.height / 2 - cRect.top,
          'rgba(180,200,240,0.35)', '1.5', '', 'rp-arrowhead',
        );
      }
    }

    // Inter-initiative relay arrows (analyst pipeline)
    if (showRelayArrows) {
      const byEmp = new Map<string, AssignmentOut[]>();
      for (const a of assignments) {
        if (a.phase !== 'analyst' || !a.employee_id || !a.start_date) continue;
        if (!byEmp.has(a.employee_id)) byEmp.set(a.employee_id, []);
        byEmp.get(a.employee_id)!.push(a);
      }

      for (const [, empAssignments] of byEmp) {
        const byItemEmp = new Map<string, AssignmentOut[]>();
        for (const a of empAssignments) {
          if (!byItemEmp.has(a.backlog_item_id)) byItemEmp.set(a.backlog_item_id, []);
          byItemEmp.get(a.backlog_item_id)!.push(a);
        }
        const orderedItems = [...byItemEmp.entries()].sort((a, b) => {
          const aStart = a[1].reduce((mn, x) => x.start_date! < mn ? x.start_date! : mn, a[1][0].start_date!);
          const bStart = b[1].reduce((mn, x) => x.start_date! < mn ? x.start_date! : mn, b[1][0].start_date!);
          return aStart.localeCompare(bStart);
        });

        for (let i = 0; i < orderedItems.length - 1; i++) {
          const [fromItemId, fromParts] = orderedItems[i];
          const [toItemId] = orderedItems[i + 1];
          const maxPart = Math.max(...fromParts.map(a => a.part_number));
          const fromEl = rowRefs.current.get(`${fromItemId}-analyst-${maxPart}`);
          const toEl = rowRefs.current.get(`${toItemId}-analyst-1`);
          if (!fromEl || !toEl) continue;

          const fRect = fromEl.getBoundingClientRect();
          const tRect = toEl.getBoundingClientRect();
          drawArrow(
            fRect.right - cRect.left,
            fRect.top + fRect.height / 2 - cRect.top,
            tRect.left - cRect.left,
            tRect.top + tRect.height / 2 - cRect.top,
            'rgba(0,201,200,0.55)', '1.5', '5 3', 'rp-relay-arrowhead',
          );
        }
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
    />
  );
}
