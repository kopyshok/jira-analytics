import { useEffect, useRef } from 'react';
import type { AssignmentOut, DependencyOut } from '../../api/resourcePlanning';

interface Props {
  assignments: AssignmentOut[];
  rowRefs: React.MutableRefObject<Map<string, HTMLElement>>;
  containerRef: React.RefObject<HTMLDivElement>;
  showRelayArrows?: boolean;
  manualDependencies?: DependencyOut[];
  onDeleteDependency?: (depId: string) => void;
  highlightedEmployeeId?: string | null;
}

const ANALYST_ROLE_CODES_ARROW = new Set([
  'аналитик', 'analyst', 'an', 'рп', 'rp', 'консультант', 'consultant',
]);
const DEV_ROLE_CODES_ARROW = new Set(['разработчик', 'developer', 'dev', 'программист']);

export default function DependencyArrows({
  assignments,
  rowRefs,
  containerRef,
  showRelayArrows = true,
  manualDependencies = [],
  onDeleteDependency,
  highlightedEmployeeId,
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
    marker.setAttribute('markerWidth', '9');
    marker.setAttribute('markerHeight', '6');
    marker.setAttribute('refX', '8');
    marker.setAttribute('refY', '3');
    marker.setAttribute('orient', 'auto');
    const poly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    poly.setAttribute('points', '0 0, 9 3, 0 6');
    poly.setAttribute('fill', '#7aa7ff');
    marker.appendChild(poly);
    defs.appendChild(marker);

    const relayMarker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
    relayMarker.setAttribute('id', 'rp-relay-arrowhead');
    relayMarker.setAttribute('markerWidth', '9');
    relayMarker.setAttribute('markerHeight', '6');
    relayMarker.setAttribute('refX', '8');
    relayMarker.setAttribute('refY', '3');
    relayMarker.setAttribute('orient', 'auto');
    const relayPoly = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    relayPoly.setAttribute('points', '0 0, 9 3, 0 6');
    relayPoly.setAttribute('fill', '#00e6c0');
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
      className?: string,
    ) {
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      // Orthogonal routing через gutter между строками:
      //  source.right → exit stub (6px вправо) → вертикаль в gutter ниже/выше
      //  source row → горизонталь в gutter → вертикаль в столбце слева от
      //  target → горизонтальный заход 14px к marker.
      //  Гарантируется длинная горизонтальная «полка» перед стрелкой и
      //  отсутствие пересечений с барами промежуточных строк (gutter живёт
      //  на границе строк, а столбец target.left-14 обычно свободен).
      const dy = y2 - y1;
      const EXIT_STUB = 6;        // отступ вправо от source перед спуском
      const APPROACH = 14;        // длина горизонтальной «полки» перед target
      const GUTTER_OFFSET = 18;   // полу-строка (ROW_HEIGHT ≈ 32–36)
      const r = 4;
      const vSign = dy >= 0 ? 1 : -1;
      let d: string;
      if (Math.abs(dy) < 1) {
        d = `M${x1},${y1} L${x2},${y2}`;
      } else {
        // Универсальная 6-сегментная схема:
        //   right(stub) → vert(gutter) → horiz(gutter) → vert(approach) → right(polkа)
        // Корректно работает и когда target правее source (Z), и когда
        // target ровно под source/левее (loop-around-left).
        const exitX = x1 + EXIT_STUB;
        const enterX = x2 - APPROACH;
        const gutterY = y1 + vSign * GUTTER_OFFSET;
        const hSign = enterX >= exitX ? 1 : -1; // направление горизонтали в gutter
        const rr = Math.max(
          1,
          Math.min(
            r,
            Math.abs(gutterY - y1) / 2,
            Math.abs(enterX - exitX) / 2 || r,
            Math.abs(y2 - gutterY) / 2,
            Math.abs(x2 - enterX) / 2,
          ),
        );
        d =
          `M${x1},${y1}` +
          ` L${exitX - rr},${y1}` +
          ` Q${exitX},${y1} ${exitX},${y1 + vSign * rr}` +
          ` L${exitX},${gutterY - vSign * rr}` +
          ` Q${exitX},${gutterY} ${exitX + hSign * rr},${gutterY}` +
          ` L${enterX - hSign * rr},${gutterY}` +
          ` Q${enterX},${gutterY} ${enterX},${gutterY + vSign * rr}` +
          ` L${enterX},${y2 - vSign * rr}` +
          ` Q${enterX},${y2} ${enterX + rr},${y2}` +
          ` L${x2},${y2}`;
      }
      path.setAttribute('d', d);
      path.setAttribute('stroke', color);
      path.setAttribute('stroke-width', width);
      path.setAttribute('fill', 'none');
      path.setAttribute('stroke-linecap', 'round');
      path.setAttribute('stroke-linejoin', 'round');
      if (dashArray) path.setAttribute('stroke-dasharray', dashArray);
      path.setAttribute('marker-end', `url(#${markerId})`);
      if (className) path.setAttribute('class', className);
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
          '#7aa7ff', '2', '', 'rp-arrowhead',
        );
      }
    }

    // Resource-flow arrows внутри инициативы: analyst-last → opo-an-1, dev-last → opo-dev-1.
    // Показывают как ресурс «перетекает» с обычной фазы на свой кусок ОПЭ.
    for (const [, itemAssignments] of byItem) {
      const analystLast = itemAssignments
        .filter(a => a.phase === 'analyst')
        .sort((a, b) => b.part_number - a.part_number)[0];
      const devLast = itemAssignments
        .filter(a => a.phase === 'dev')
        .sort((a, b) => b.part_number - a.part_number)[0];
      const opoAnalyst = itemAssignments.find(a =>
        a.phase === 'opo' && a.part_number === 1
        && ANALYST_ROLE_CODES_ARROW.has((a.employee_role ?? '').toLowerCase())
      );
      const opoDev = itemAssignments.find(a =>
        a.phase === 'opo' && a.part_number === 1
        && DEV_ROLE_CODES_ARROW.has((a.employee_role ?? '').toLowerCase())
      );

      const drawResource = (
        from: AssignmentOut | undefined,
        to: AssignmentOut | undefined,
        roleSuffix: 'an' | 'dev',
      ) => {
        if (!from || !to) return;
        const fromEl = rowRefs.current.get(`${from.backlog_item_id}-${from.phase}-${from.part_number}`);
        const toEl = rowRefs.current.get(`${to.backlog_item_id}-opo-${roleSuffix}-1`);
        if (!fromEl || !toEl) return;
        const fRect = fromEl.getBoundingClientRect();
        const tRect = toEl.getBoundingClientRect();
        const isFaded =
          !!highlightedEmployeeId && from.employee_id !== highlightedEmployeeId;
        const color = isFaded ? 'rgba(0,230,192,0.18)' : '#00e6c0';
        drawArrow(
          fRect.right - cRect.left,
          fRect.top + fRect.height / 2 - cRect.top,
          tRect.left - cRect.left,
          tRect.top + tRect.height / 2 - cRect.top,
          color, '2', '8 4', 'rp-relay-arrowhead',
          undefined,
          isFaded ? undefined : 'rp-flow',
        );
      };

      drawResource(analystLast, opoAnalyst, 'an');
      drawResource(devLast, opoDev, 'dev');
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
            '#00e6c0', '2', '8 4', 'rp-relay-arrowhead',
            undefined,
            'rp-flow',
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
  }, [assignments, manualDependencies, showRelayArrows, onDeleteDependency, containerRef, rowRefs, highlightedEmployeeId]);

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
