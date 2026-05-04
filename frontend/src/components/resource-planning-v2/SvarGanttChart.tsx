import { useEffect, useRef } from 'react';
import Gantt from 'frappe-gantt';
import './frappe-gantt-base.css';
import './svar-dark.css';
import type { AssignmentOut } from '../../api/resourcePlanning';

interface FrappeTask {
  id: string;
  name: string;
  start: string;  // YYYY-MM-DD
  end: string;
  progress: number;
  dependencies?: string;  // comma-separated FrappeTask.id
  custom_class?: string;
}

interface Props {
  assignments: AssignmentOut[];
  viewMode: 'task' | 'employee';
}

function fmtDate(d: string | null): string | null {
  if (!d) return null;
  return d.slice(0, 10);  // strip time if any
}

function buildTasks(assignments: AssignmentOut[], viewMode: 'task' | 'employee'): FrappeTask[] {
  const valid = assignments.filter(a => a.start_date && a.end_date);
  if (viewMode === 'task') {
    return valid.map((a, idx) => ({
      id: `t-${a.id || idx}`,
      name: `${a.backlog_item_key ?? a.backlog_item_id.slice(0, 6)} · ${a.phase}${a.employee_name ? ' · ' + a.employee_name : ''}`,
      start: fmtDate(a.start_date)!,
      end: fmtDate(a.end_date)!,
      progress: 0,
      custom_class: a.is_pinned ? 'pinned' : `phase-${a.phase}`,
    }));
  }
  // viewMode === 'employee'
  // Frappe doesn't natively group, so we just sort by employee_name and prefix the name
  const sorted = [...valid].sort((a, b) => (a.employee_name ?? '~').localeCompare(b.employee_name ?? '~'));
  return sorted.map((a, idx) => ({
    id: `e-${a.id || idx}`,
    name: `${a.employee_name ?? '(пул)'} — ${a.backlog_item_key ?? '?'} · ${a.phase}`,
    start: fmtDate(a.start_date)!,
    end: fmtDate(a.end_date)!,
    progress: 0,
    custom_class: `phase-${a.phase}`,
  }));
}

export default function SvarGanttChart({ assignments, viewMode }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const ganttRef = useRef<Gantt | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const tasks = buildTasks(assignments, viewMode);
    if (tasks.length === 0) {
      // Frappe doesn't handle empty arrays well — clear the container
      ref.current.innerHTML = '<div style="color:#8ab0d8;padding:24px">Нет задач для отображения</div>';
      return;
    }
    // Recreate on every change — simpler than diffing
    ref.current.innerHTML = '';
    try {
      ganttRef.current = new Gantt(ref.current, tasks, {
        view_mode: 'Day',
        bar_height: 24,
        bar_corner_radius: 3,
        padding: 18,
        popup_on: 'hover',
      });
    } catch (e) {
      console.error('Gantt render error', e);
    }
  }, [assignments, viewMode]);

  return (
    <div style={{ height: 600, background: '#0f2340', borderRadius: 8, padding: 8, overflow: 'auto' }}>
      <div ref={ref} className="frappe-gantt-host" />
    </div>
  );
}
