import type { BacklogItemResponse, InPlanRole } from '../types/api';

export type { InPlanRole };

type RoleSource = Partial<Pick<BacklogItemResponse, 'in_plan_role' | 'planning_mode'>>;

/** Строка списка или её дочерняя строка. */
export type InPlanRow = RoleSource & { id: string; included_in_planning: boolean };

/** Роль переключателя «В план» — её считает сервер по всему бэклогу: список
 *  с фильтром команды или на другой вкладке не видит всей группы.
 *  `mode` — режим, выбранный в модалке и ещё не сохранённый: до ответа сервера
 *  роль родителя группы следует ему. */
export function inPlanRole(r: RoleSource, mode = r.planning_mode): InPlanRole {
  const role = r.in_plan_role ?? 'regular';
  // Эпику внутри инициативы «целиком» и инициативе нескольких команд
  // собственный режим роли не меняет.
  if (mode === r.planning_mode || role === 'inert' || role === 'by_epics_locked') return role;
  return mode === 'by_epics' ? 'by_epics' : 'regular';
}

export function inPlanHint(role: InPlanRole, included: boolean): string {
  if (role === 'inert') return 'Инициатива планируется целиком — часы эпиков уже в ней';
  if (role === 'by_epics_locked') return 'Инициатива нескольких команд планируется только по эпикам';
  if (role === 'by_epics' && !included) {
    return 'Планируется по эпикам: в сценарий идут её эпики. Включите, чтобы добавить и саму инициативу';
  }
  return included ? 'Попадает в сценарии' : 'Не попадает в сценарии';
}

export const inPlanDisabled = (role: InPlanRole, included: boolean) =>
  role === 'inert' || (role === 'by_epics_locked' && !included);

/** «Не в плане» — только выбор пользователя: выключенная инициатива по эпикам
 *  и эпик внутри инициативы «целиком» из плана ничего не убирают. */
export const isOffPlan = (role: InPlanRole, included: boolean) =>
  role === 'regular' && !included;

/** Только строки «не в плане»: такой родитель — со всеми дочками,
 *  остальные — только с такими дочками. */
export function filterOffPlan(
  rows: BacklogItemResponse[] | undefined,
  offPlan: (r: InPlanRow) => boolean,
): BacklogItemResponse[] | undefined {
  return rows?.flatMap((r) => {
    if (offPlan(r)) return [r];
    const kids = (r.children ?? []).filter(offPlan);
    return kids.length ? [{ ...r, children: kids }] : [];
  });
}

export function countOffPlan(
  rows: BacklogItemResponse[] | undefined,
  offPlan: (r: InPlanRow) => boolean,
): number {
  return (rows ?? []).reduce(
    (n, r) =>
      n + (offPlan(r) ? 1 : 0)
      + (r.children ?? []).filter(offPlan).length,
    0,
  );
}
