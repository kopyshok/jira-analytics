import type { DeskIssue } from '../../api/teamDesk';

/**
 * Какая строка очереди разложена по задачам: вся очередь, только задачи с
 * исполнителем-владельцем, либо разбор не включён.
 */
export type QueueScope = 'all' | 'assigned' | null;

export const QUEUE_SCOPE_LABEL: Record<'all' | 'assigned', string> = {
  all: 'в очереди',
  assigned: 'в очереди к выполнению',
};

/** Попадает ли задача в разложенную строку очереди. */
export function inQueueScope(issue: DeskIssue, scope: QueueScope): boolean {
  if (!scope) return true;
  if (!issue.in_queue) return false;
  return scope === 'all' || issue.assigned_to_owner;
}
