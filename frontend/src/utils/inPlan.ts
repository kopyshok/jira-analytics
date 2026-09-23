import type { BacklogItemResponse } from '../types/api';

/** Что значит переключатель «В план» для строки целевых задач.
 *  - regular — решает, идёт ли задача в сценарии;
 *  - inert — эпик внутри инициативы «целиком»: его часы уже в ней, переключатель ничего не меняет;
 *  - by_epics — инициатива по эпикам: переключатель только про саму инициативу, эпики — своими;
 *  - by_epics_locked — инициатива нескольких команд: только по эпикам, саму не включить. */
export type InPlanRole = 'regular' | 'inert' | 'by_epics' | 'by_epics_locked';

type RoleSource = Partial<Pick<
  BacklogItemResponse, 'has_children_in_backlog' | 'planning_mode' | 'planning_mode_locked'
>>;

/** Строка списка или её дочерняя строка. */
export type InPlanRow = RoleSource & { id: string; included_in_planning: boolean };

/** Режим группы с учётом блокировки мультикомандных — как на сервере. */
const plannedByEpics = (r: RoleSource, mode = r.planning_mode) =>
  mode === 'by_epics' || !!r.planning_mode_locked;

/** `mode` — локальный (ещё не сохранённый) режим из модалки. */
export function inPlanRole(r: RoleSource, inert: boolean, mode = r.planning_mode): InPlanRole {
  if (inert) return 'inert';
  if (!r.has_children_in_backlog || !plannedByEpics(r, mode)) return 'regular';
  return r.planning_mode_locked ? 'by_epics_locked' : 'by_epics';
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

/** Дочки инициатив «целиком», кроме Дискавери. */
export function inertEpicIds(rows: BacklogItemResponse[]): Set<string> {
  const ids = new Set<string>();
  for (const r of rows) {
    if (plannedByEpics(r)) continue;
    for (const c of r.children ?? []) if (!c.is_service_epic) ids.add(c.id);
  }
  return ids;
}

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
