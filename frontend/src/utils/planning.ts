import type { AllocationResponse } from '../types/api';
import { effectiveEstimate } from './allocationEstimates';

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
    const eff = effectiveEstimate(a);
    const r = a.opo_analyst_ratio ?? 0.5;
    d.analyst += eff.analyst + eff.opo * r;
    d.dev += eff.dev + eff.opo * (1 - r);
    d.qa += eff.qa;
  }
  return d;
}

type EmployeeLike = { employee_id: string; role: string | null; display_name: string };

const ANALYST_LIKE_ROLES = new Set(['analyst', 'RP', 'project_manager', 'consultant']);

/**
 * Персональная нагрузка по сотрудникам: {employee_id: часы}.
 *
 * Разработчик из колонки «Разработчик» получает часы разработки. Исполнитель
 * строки («Аналитик») — часы своего типа работ по роли: аналитик, РП и
 * консультант «закрывают» анализ, разработчик — разработку, тестировщик —
 * тестирование. Колонка «Разработчик» заполнена — исполнитель встаёт на
 * анализ при любой роли, а совпавший с разработчиком получает только
 * разработку (как в ресурсном плане). Остальные часы уходят в ролевые пулы.
 */
export function demandByEmployee(
  allocations: AllocationResponse[],
  employees: EmployeeLike[],
): Record<string, number> {
  const result: Record<string, number> = {};
  const add = (id: string, hours: number) => {
    result[id] = (result[id] ?? 0) + hours;
  };
  for (const alloc of allocations) {
    if (!alloc.included) continue;
    const eff = effectiveEstimate(alloc);
    const r = alloc.opo_analyst_ratio ?? 0.5;
    const analystPortion = eff.analyst + eff.opo * r;
    const devPortion = eff.dev + eff.opo * (1 - r);
    const devId = alloc.developer_employee_id;
    if (devId) add(devId, devPortion);

    let emp = alloc.assignee_employee_id
      ? employees.find((e) => e.employee_id === alloc.assignee_employee_id)
      : undefined;
    // Фолбэк: если у задачи нет связки employee_id, но есть display_name
    // (бывает, когда бэклог подтянул задачу из Jira без смапленного Employee),
    // ищем сотрудника по имени в команде сценария. Сопоставление толерантное:
    // сравниваем множества слов — порядок и лишние слова не мешают
    // («Копышков Николай» ↔ «Копышков Николай Сергеевич»).
    if (!emp && alloc.assignee_display_name) {
      const tokens = (s: string) =>
        new Set(s.toLowerCase().split(/\s+/).filter((t) => t.length >= 3));
      const need = tokens(alloc.assignee_display_name);
      if (need.size > 0) {
        emp = employees.find((e) => {
          const have = tokens(e.display_name);
          let hit = 0;
          for (const t of need) if (have.has(t)) hit += 1;
          return hit >= Math.min(2, need.size);
        });
      }
    }
    if (!emp?.role || emp.employee_id === devId) continue;
    const role = emp.role;
    const personalLoad =
      devId || ANALYST_LIKE_ROLES.has(role)
        ? analystPortion
        : role === 'dev'
          ? devPortion
          : role === 'qa'
            ? eff.qa
            : 0;
    add(emp.employee_id, personalLoad);
  }
  return result;
}

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
    const eff = effectiveEstimate(a);
    const r = a.opo_analyst_ratio ?? 0.5;

    const analystPortion = eff.analyst + eff.opo * r;
    const devPortion = eff.dev + eff.opo * (1 - r);
    const qaPortion = eff.qa;

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
