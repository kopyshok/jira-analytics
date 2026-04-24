import type { AllocationResponse } from '../types/api';

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
 * Считает потребность по роли ИСПОЛНИТЕЛЯ, а не по типу оценки задачи.
 * Если РП делает задачу с аналитическими часами — часы идут в пул РП, не аналитика.
 * Без сопоставленного сотрудника (нет assignee или нет роли) — фолбэк на estimate-based.
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
    const emp = employees.find((e) => e.employee_id === a.assignee_employee_id);
    // Используем роль из найденного сотрудника, иначе — денормализованную роль из
    // аллокации (assignee может быть из другой команды и отсутствовать в пуле).
    const role = emp?.role ?? a.assignee_role ?? null;
    if (role) {
      const hours =
        role === 'analyst'
          ? ea + eo * r
          : role === 'dev'
            ? ed + eo * (1 - r)
            : role === 'qa'
              ? eq
              : ea + ed + eq + eo; // consultant / project_manager / other
      d[role] = (d[role] ?? 0) + hours;
    } else if (!a.assignee_employee_id) {
      // Нет конкретного исполнителя — распределяем по типу оценки.
      d['analyst'] = (d['analyst'] ?? 0) + ea + eo * r;
      d['dev'] = (d['dev'] ?? 0) + ed + eo * (1 - r);
      d['qa'] = (d['qa'] ?? 0) + eq;
    }
    // Если исполнитель задан, но роль неизвестна — не добавляем в аналитик.
  }
  return d;
}
