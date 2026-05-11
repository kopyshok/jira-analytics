import { useEffect, useRef } from 'react';
import type { AssignmentOut, DependencyOut } from '../../api/resourcePlanning';

interface Props {
  assignments: AssignmentOut[];
  rowRefs: React.MutableRefObject<Map<string, HTMLElement>>;
  containerRef: React.RefObject<HTMLDivElement>;
  showRelayArrows?: boolean;
  manualDependencies?: DependencyOut[];
  onDeleteDependency?: (depId: string) => void;
}

export default function DependencyArrows({
  assignments,
  rowRefs,
  containerRef,
  showRelayArrows = true,
  manualDependencies = [],
  onDeleteDependency,
}: Props) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const svg = svgRef.current;
    const container = containerRef.current;
    if (!svg || !container) return;

    // Дать DOM settle после прихода новых assignments — rowRefs обновляются
    // в ref-callbacks PhaseBar, иногда useEffect выстреливает до апдейта.
    let cancelled = false;
    const raf1 = requestAnimationFrame(() => {
      if (cancelled) return;
      const raf2 = requestAnimationFrame(() => {
        if (cancelled) return;
        draw();
      });
      (raf1 as unknown as { _inner?: number })._inner = raf2;
    });

    function draw() {
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

    const manualMarker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
    manualMarker.setAttribute('id', 'rp-manual-arrowhead');
    manualMarker.setAttribute('markerWidth', '7');
    manualMarker.setAttribute('markerHeight', '5');
    manualMarker.setAttribute('refX', '7');
    manualMarker.setAttribute('refY', '2.5');
    manualMarker.setAttribute('orient', 'auto');
    const manualPoly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    manualPoly.setAttribute('points', '0 0, 7 2.5, 0 5');
    manualPoly.setAttribute('fill', '#ff7a45');
    manualMarker.appendChild(manualPoly);
    defs.appendChild(manualMarker);

    svg.appendChild(defs);

    const cRect = container.getBoundingClientRect();

    function drawArrow(
      x1: number, y1: number, x2: number, y2: number,
      color: string, width: string, dashArray: string, markerId: string,
      onClick?: () => void,
    ) {
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      // Orthogonal L-shape с маленькими радиусами на сгибах — не пересекает
      // соседние bar-ы, выглядит чище чем S-curve.
      const dx = x2 - x1;
      const dy = y2 - y1;
      const stub = Math.min(14, Math.max(6, Math.abs(dx) / 4));
      const r = 4; // радиус скругления угла
      let d: string;
      if (Math.abs(dy) < 1) {
        d = `M${x1},${y1} L${x2},${y2}`;
      } else if (dx >= stub * 2) {
        // право → вниз → право
        const midX = x1 + stub;
        const sweep = dy > 0 ? 1 : 0;
        d =
          `M${x1},${y1}` +
          ` L${midX - r},${y1}` +
          ` Q${midX},${y1} ${midX},${y1 + (dy > 0 ? r : -r)}` +
          ` L${midX},${y2 - (dy > 0 ? r : -r)}` +
          ` Q${midX},${y2} ${midX + r},${y2}` +
          ` L${x2},${y2}`;
        void sweep;
      } else {
        // bar справа от source конец, идём вниз/вверх с минимальным stub
        const midX = x1 + stub;
        d =
          `M${x1},${y1}` +
          ` L${midX - r},${y1}` +
          ` Q${midX},${y1} ${midX},${y1 + (dy > 0 ? r : -r)}` +
          ` L${midX},${y2 - (dy > 0 ? r : -r)}` +
          ` Q${midX},${y2} ${midX + r},${y2}` +
          ` L${x2},${y2}`;
      }
      path.setAttribute('d', d);
      path.setAttribute('stroke', color);
      path.setAttribute('stroke-width', width);
      path.setAttribute('fill', 'none');
      path.setAttribute('stroke-linejoin', 'round');
      if (dashArray) path.setAttribute('stroke-dasharray', dashArray);
      path.setAttribute('marker-end', `url(#${markerId})`);
      if (onClick) {
        path.setAttribute('style', 'pointer-events: stroke; cursor: pointer;');
        path.addEventListener('click', onClick);
      }
      (svg as SVGSVGElement).appendChild(path);
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
          'rgba(140,170,210,0.25)', '1', '', 'rp-arrowhead',
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
          const maxPart = Math.max(...fromParts.map(a => a.part_number), 0);
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
            'rgba(0,201,200,0.40)', '1', '4 3', 'rp-relay-arrowhead',
          );
        }
      }
    }

    // Manual user-drawn dependencies between initiatives
    if (manualDependencies.length > 0) {
      for (const dep of manualDependencies) {
        const fromEl = rowRefs.current.get(dep.from_item_id);
        const toEl = rowRefs.current.get(dep.to_item_id);
        if (!fromEl || !toEl) continue;
        const fRect = fromEl.getBoundingClientRect();
        const tRect = toEl.getBoundingClientRect();
        const startSide = (dep.dep_type === 'SS' || dep.dep_type === 'SF')
          ? fRect.left - cRect.left
          : fRect.right - cRect.left;
        const endSide = (dep.dep_type === 'SS' || dep.dep_type === 'FS')
          ? tRect.left - cRect.left
          : tRect.right - cRect.left;
        drawArrow(
          startSide,
          fRect.top + fRect.height / 2 - cRect.top,
          endSide,
          tRect.top + tRect.height / 2 - cRect.top,
          '#ff7a45', '2', '', 'rp-manual-arrowhead',
          onDeleteDependency ? () => {
            // Confirm via window.confirm — simple, no extra deps
            if (window.confirm(`Удалить связь ${dep.dep_type}?`)) {
              onDeleteDependency(dep.id);
            }
          } : undefined,
        );
      }
    }
    }

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf1);
    };
  }, [assignments, manualDependencies, showRelayArrows, onDeleteDependency, containerRef, rowRefs]);

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
