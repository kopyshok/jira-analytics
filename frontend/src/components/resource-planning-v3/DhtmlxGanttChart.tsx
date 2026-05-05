import { useEffect, useRef } from 'react';
// The DHTMLX ES bundle only exports the singleton `gantt`; `Gantt` (instance factory)
// is not available in the ES module. Since only one DhtmlxGanttChart is mounted at a
// time, using the singleton is safe.
import { gantt } from 'dhtmlx-gantt';
import 'dhtmlx-gantt/codebase/dhtmlxgantt.css';
import './dhtmlx-dark-overrides.css';
import type { AssignmentOut } from '../../api/resourcePlanning';

interface Props {
  assignments: AssignmentOut[];
  dependencies?: Array<{ from_item_id: string; to_item_id: string; dep_type: string }>;
  viewMode: 'day' | 'week' | 'month';
  quarter: string;
  year: number;
}

const SCALES: Record<string, Array<{ unit: string; step: number; format: string }>> = {
  day: [
    { unit: 'month', step: 1, format: '%F %Y' },
    { unit: 'day', step: 1, format: '%d' },
  ],
  week: [
    { unit: 'month', step: 1, format: '%F %Y' },
    { unit: 'week', step: 1, format: '#%W' },
  ],
  month: [
    { unit: 'year', step: 1, format: '%Y' },
    { unit: 'month', step: 1, format: '%F' },
  ],
};

const DEP_TYPE: Record<string, string> = { FS: '0', SS: '1', FF: '2', SF: '3' };

function dateDiffDays(start: string, end: string): number {
  const s = new Date(start), e = new Date(end);
  return Math.max(1, Math.round((e.getTime() - s.getTime()) / 86400000) + 1);
}

export default function DhtmlxGanttChart({
  assignments,
  dependencies = [],
  viewMode,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const initialised = useRef(false);

  // Init / reinit when viewMode changes
  useEffect(() => {
    if (!containerRef.current) return;
    if (initialised.current) {
      // Only update scales and re-render when viewMode changes after first init
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (gantt.config as any).scales = SCALES[viewMode];
      gantt.render();
      return;
    }
    gantt.config.date_format = '%Y-%m-%d';
    gantt.config.readonly = true;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (gantt.config as any).scales = SCALES[viewMode];
    gantt.config.row_height = 32;
    gantt.config.bar_height = 22;
    gantt.config.scale_height = 50;
    // Phase-coloured bars via CSS class
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    gantt.templates.task_class = (_s: any, _e: any, task: any) =>
      `phase-${(task as Record<string, unknown>).phase ?? 'default'}`;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    gantt.templates.task_text = (_s: any, _e: any, task: any) => (task.text as string) ?? '';
    gantt.init(containerRef.current);
    initialised.current = true;
    return () => {
      try { gantt.clearAll(); } catch { /* ignore */ }
      initialised.current = false;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewMode]);

  // Parse data whenever assignments / dependencies change
  useEffect(() => {
    if (!initialised.current) return;

    // Group by backlog_item_id → parent project rows + phase children
    const itemMap = new Map<string, AssignmentOut[]>();
    for (const a of assignments) {
      if (!a.start_date || !a.end_date) continue;
      const arr = itemMap.get(a.backlog_item_id) ?? [];
      arr.push(a);
      itemMap.set(a.backlog_item_id, arr);
    }

    const data: Array<Record<string, unknown>> = [];
    itemMap.forEach((items, itemId) => {
      const starts = items.map(i => i.start_date!).sort();
      const ends = items.map(i => i.end_date!).sort();
      data.push({
        id: `p-${itemId}`,
        text: items[0].backlog_item_key ?? itemId.slice(0, 6),
        start_date: starts[0],
        duration: dateDiffDays(starts[0], ends[ends.length - 1]),
        type: 'project',
        open: true,
      });
      for (const a of items) {
        data.push({
          id: a.id,
          text: `${a.phase}${a.employee_name ? ' · ' + a.employee_name : ''}`,
          start_date: a.start_date,
          duration: dateDiffDays(a.start_date!, a.end_date!),
          parent: `p-${itemId}`,
          phase: a.phase,
          progress: 0,
        });
      }
    });

    const links = dependencies
      .filter(d => DEP_TYPE[d.dep_type] !== undefined)
      .map((d, i) => ({
        id: `link-${i}`,
        source: `p-${d.from_item_id}`,
        target: `p-${d.to_item_id}`,
        type: DEP_TYPE[d.dep_type],
      }));

    gantt.clearAll();
    gantt.parse({ data, links });
  }, [assignments, dependencies]);

  return (
    <div
      ref={containerRef}
      style={{ width: '100%', height: 600, background: '#0f2340', borderRadius: 8 }}
      className="dhtmlx-gantt-host"
    />
  );
}
