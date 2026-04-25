import type { AllocationResponse } from '../types/api';

/**
 * Возвращает дефицит по ролям: для ролей, где demand > avail, вернёт
 * положительное число часов недостачи. Роли без дефицита в результате
 * не присутствуют. Округляет до целого.
 *
 * @example
 *   computeDeficitByRole({ analyst: 100 }, { analyst: 120 }) // { analyst: 20 }
 *   computeDeficitByRole({ analyst: 100 }, { analyst: 80 })  // {}
 */
export function computeDeficitByRole(
  available: Record<string, number>,
  demand: Record<string, number>,
): Record<string, number> {
  const out: Record<string, number> = {};
  for (const role of Object.keys(available)) {
    const used = demand[role] ?? 0;
    const remaining = available[role] - used;
    if (remaining < 0) {
      out[role] = Math.round(-remaining);
    }
  }
  return out;
}

/** Считает потребность по ролям (аналитик/разработчик/тестировщик)
 *  на основе списка раскладок. Учитываются только включённые элементы.
 *  Повторяет логику backend _demand_by_role. */
export function demandByRole(allocations: AllocationResponse[]): Record<string, number> {
  const d = { analyst: 0, dev: 0, qa: 0 };
  for (const a of allocations) {
    if (!a.included) continue;
    const ea = a.estimate_analyst_hours ?? 0;
    const ed = a.estimate_dev_hours ?? 0;
    const eq = a.estimate_qa_hours ?? 0;
    const eo = a.estimate_opo_hours ?? 0;
    const r = a.opo_analyst_ratio ?? 0.5;
    d.analyst += ea + eo * r;
    d.dev += ed + eo * (1 - r);
    d.qa += eq;
  }
  return d;
}

type EmployeeLike = { employee_id: string; role: string | null; display_name: string };

/**
 * Считает потребность по ролям с учётом исполнителя.
 *
 * Часы задачи всегда раскладываются по своим типам работы:
 *   - аналитический объём = ea + eo * r
 *   - программистский объём = ed + eo * (1 - r)
 *   - тестировочный объём = eq
 *
 * Особенность: если задача назначена на РП или Консультанта, аналитический
 * объём «закрывает» эта роль (на неё уходят часы аналитика), а часы
 * программиста и тестировщика по-прежнему идут в свои пулы.
 */
export function demandByAssigneeRole(
  allocations: AllocationResponse[],
  employees: EmployeeLike[],
): Record<string, number> {
  const d: Record<string, number> = {};
  for (const a of allocations) {
    if (!a.included) continue;
    const ea = a.estimate_analyst_hours ?? 0;
    const ed = a.estimate_dev_hours ?? 0;
    const eq = a.estimate_qa_hours ?? 0;
    const eo = a.estimate_opo_hours ?? 0;
    const r = a.opo_analyst_ratio ?? 0.5;

    const analystPortion = ea + eo * r;
    const devPortion = ed + eo * (1 - r);
    const qaPortion = eq;

    // Роль исполнителя: из пула команды или денормализованная (если ассигни вне
    // команды), либо разрешённая на бэке по имени из Jira.
    const emp = employees.find((e) => e.employee_id === a.assignee_employee_id);
    const role = emp?.role ?? a.assignee_role ?? null;
    const isAnalystSubstitute =
      role === 'RP' || role === 'project_manager' || role === 'consultant';
    const analystTarget = isAnalystSubstitute ? (role as string) : 'analyst';

    d[analystTarget] = (d[analystTarget] ?? 0) + analystPortion;
    d['dev'] = (d['dev'] ?? 0) + devPortion;
    d['qa'] = (d['qa'] ?? 0) + qaPortion;
  }
  return d;
}
