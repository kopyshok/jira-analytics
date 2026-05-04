import { Gantt, Willow } from 'wx-react-gantt';
import 'wx-react-gantt/dist/gantt.css';
import './svar-dark.css';

import type { AssignmentOut } from '../../api/resourcePlanning';

interface GanttTask {
  id: string;
  text: string;
  start: Date;
  end: Date;
  type: 'task' | 'summary' | 'milestone';
  parent?: string;
  open?: boolean;
  progress?: number;
}

interface Props {
  assignments: AssignmentOut[];
  viewMode: 'task' | 'employee';
}

function parseDate(iso: string): Date {
  return new Date(iso);
}

function buildTasksByTask(assignments: AssignmentOut[]): GanttTask[] {
  const valid = assignments.filter(a => a.start_date && a.end_date);
  const groups = new Map<string, AssignmentOut[]>();
  for (const a of valid) {
    const list = groups.get(a.backlog_item_id) ?? [];
    list.push(a);
    groups.set(a.backlog_item_id, list);
  }

  const tasks: GanttTask[] = [];
  for (const [itemId, items] of groups) {
    const starts = items.map(a => parseDate(a.start_date!).getTime());
    const ends = items.map(a => parseDate(a.end_date!).getTime());
    const parentStart = new Date(Math.min(...starts));
    const parentEnd = new Date(Math.max(...ends));
    const label = items[0].backlog_item_key ?? itemId.slice(0, 6);
    tasks.push({
      id: `item-${itemId}`,
      text: label,
      start: parentStart,
      end: parentEnd,
      type: 'summary',
      open: false,
    });
    for (const a of items) {
      const phaseLabels: Record<string, string> = {
        analyst: 'Анализ',
        dev: 'Разработка',
        qa: 'Тестирование',
        opo: 'ОПЭ',
      };
      tasks.push({
        id: a.id,
        text: phaseLabels[a.phase] ?? a.phase,
        start: parseDate(a.start_date!),
        end: parseDate(a.end_date!),
        type: 'task',
        parent: `item-${itemId}`,
      });
    }
  }
  return tasks;
}

function buildTasksByEmployee(assignments: AssignmentOut[]): GanttTask[] {
  const valid = assignments.filter(a => a.start_date && a.end_date);
  const groups = new Map<string, AssignmentOut[]>();
  for (const a of valid) {
    const key = a.employee_id ?? '__pool__';
    const list = groups.get(key) ?? [];
    list.push(a);
    groups.set(key, list);
  }

  const tasks: GanttTask[] = [];
  for (const [empKey, items] of groups) {
    const starts = items.map(a => parseDate(a.start_date!).getTime());
    const ends = items.map(a => parseDate(a.end_date!).getTime());
    const parentStart = new Date(Math.min(...starts));
    const parentEnd = new Date(Math.max(...ends));
    const empName = items[0].employee_name ?? '(Пул)';
    tasks.push({
      id: `emp-${empKey}`,
      text: empName,
      start: parentStart,
      end: parentEnd,
      type: 'summary',
      open: false,
    });
    for (const a of items) {
      const itemLabel = a.backlog_item_key ?? a.backlog_item_id.slice(0, 6);
      const phaseLabels: Record<string, string> = {
        analyst: 'Анализ',
        dev: 'Разработка',
        qa: 'Тестирование',
        opo: 'ОПЭ',
      };
      tasks.push({
        id: a.id,
        text: `${itemLabel} · ${phaseLabels[a.phase] ?? a.phase}`,
        start: parseDate(a.start_date!),
        end: parseDate(a.end_date!),
        type: 'task',
        parent: `emp-${empKey}`,
      });
    }
  }
  return tasks;
}

const scales = [
  { unit: 'month', step: 1, format: 'MMMM yyyy' },
  { unit: 'day', step: 1, format: 'd' },
];

export default function SvarGanttChart({ assignments, viewMode }: Props) {
  const tasks =
    viewMode === 'task'
      ? buildTasksByTask(assignments)
      : buildTasksByEmployee(assignments);

  return (
    <div
      style={{
        height: 600,
        background: '#0f2340',
        borderRadius: 8,
        padding: 8,
        overflow: 'hidden',
      }}
    >
      <Willow>
        <Gantt tasks={tasks} links={[]} scales={scales} />
      </Willow>
    </div>
  );
}
