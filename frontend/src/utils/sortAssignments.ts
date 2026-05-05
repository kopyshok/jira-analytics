import type { AssignmentOut } from '../api/resourcePlanning';

/**
 * Сортирует строки Gantt по главному исполнителю инициативы из утверждённого
 * сценария (`scenario_assignee_employee_id`). Внутри одного исполнителя —
 * по самой ранней дате начала задачи. Задачи без assignee — в конец списка.
 *
 * Сортировка стабильная: сохраняет порядок строк одной phase внутри одной
 * инициативы (что важно для двух- и трёхфазных задач).
 */
export function sortAssignmentsByScenarioAssignee(
  assignments: AssignmentOut[],
): AssignmentOut[] {
  // Минимальная start_date на инициативу — для вторичной сортировки
  const earliestStartByItem = new Map<string, string>();
  for (const a of assignments) {
    if (!a.start_date) continue;
    const cur = earliestStartByItem.get(a.backlog_item_id);
    if (!cur || a.start_date < cur) {
      earliestStartByItem.set(a.backlog_item_id, a.start_date);
    }
  }

  // Бакетизация по item: один порядок строк per item, чтобы не разбивать фазы
  const items = new Map<string, AssignmentOut[]>();
  for (const a of assignments) {
    const arr = items.get(a.backlog_item_id) ?? [];
    arr.push(a);
    items.set(a.backlog_item_id, arr);
  }

  type Bucket = {
    itemId: string;
    rows: AssignmentOut[];
    assigneeName: string | null;
    assigneeId: string | null;
    earliest: string;
  };

  const buckets: Bucket[] = [...items.entries()].map(([itemId, rows]) => ({
    itemId,
    rows,
    assigneeName: rows[0]?.scenario_assignee_name ?? null,
    assigneeId: rows[0]?.scenario_assignee_employee_id ?? null,
    earliest: earliestStartByItem.get(itemId) ?? '￿',
  }));

  buckets.sort((a, b) => {
    // Без assignee — в конец
    if (!a.assigneeName && b.assigneeName) return 1;
    if (a.assigneeName && !b.assigneeName) return -1;
    if (a.assigneeName && b.assigneeName) {
      const cmp = a.assigneeName.localeCompare(b.assigneeName, 'ru');
      if (cmp !== 0) return cmp;
    }
    return a.earliest.localeCompare(b.earliest);
  });

  return buckets.flatMap(b => b.rows);
}
