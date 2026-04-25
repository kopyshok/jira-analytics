import type { AllocationResponse } from '../types/api';

export interface ScenarioDiffResult {
  onlyInA: AllocationResponse[];
  onlyInB: AllocationResponse[];
  common: { left: AllocationResponse; right: AllocationResponse }[];
}

/**
 * Сравнивает два списка раскладок по `backlog_item_id`. Учитываются только
 * включённые в сценарий элементы (`included === true`).
 *
 * Returns:
 *   - onlyInA  — присутствуют только в `left`
 *   - onlyInB  — присутствуют только в `right`
 *   - common   — пары (left, right) с одинаковым backlog_item_id
 */
export function diffScenarios(
  left: AllocationResponse[],
  right: AllocationResponse[],
): ScenarioDiffResult {
  const leftIncluded = left.filter((a) => a.included);
  const rightIncluded = right.filter((a) => a.included);
  const rightMap = new Map(rightIncluded.map((a) => [a.backlog_item_id, a]));
  const onlyInA: AllocationResponse[] = [];
  const common: { left: AllocationResponse; right: AllocationResponse }[] = [];
  const seen = new Set<string>();
  for (const l of leftIncluded) {
    const r = rightMap.get(l.backlog_item_id);
    if (r) {
      common.push({ left: l, right: r });
      seen.add(l.backlog_item_id);
    } else {
      onlyInA.push(l);
    }
  }
  const onlyInB = rightIncluded.filter((a) => !seen.has(a.backlog_item_id));
  return { onlyInA, onlyInB, common };
}
