import type { OtherTeamWorkOut, ReserveOut, ReserveTypeRow } from '../api/resourcePlanning';
import { fmtHours as fmtHoursRaw } from './rpBusy';

/** Сколько строк запаса в перерасходе (для красной подсветки и счётчика). */
export function overuseCount(reserve: ReserveOut | null | undefined): number {
  if (!reserve) return 0;
  return reserve.roles.reduce((n, r) => n + r.rows.filter((x) => x.overuse_hours > 0.5).length, 0);
}

/** Склонение «перерасход»: 1 перерасход, 2 перерасхода, 5 перерасходов. */
function pluralOveruse(n: number): string {
  if (n % 100 >= 11 && n % 100 <= 14) return 'перерасходов';
  const last = n % 10;
  if (last === 1) return 'перерасход';
  if (last >= 2 && last <= 4) return 'перерасхода';
  return 'перерасходов';
}

/** Склонение «задача»: 1 задача, 2 задачи, 5 задач. */
function pluralTasks(n: number): string {
  if (n % 100 >= 11 && n % 100 <= 14) return 'задач';
  const last = n % 10;
  if (last === 1) return 'задача';
  if (last >= 2 && last <= 4) return 'задачи';
  return 'задач';
}

/** Подпись числа перерасходов для шапки свёрнутого блока: «2 перерасхода». Нет перерасхода — null. */
export function overuseLabel(reserve: ReserveOut | null | undefined): string | null {
  const n = overuseCount(reserve);
  if (n === 0) return null;
  return `${n} ${pluralOveruse(n)}`;
}

/** Подпись часов: «102 ч» (округление — как в rpBusy, до десятых). */
export const fmtHours = (h: number) => `${fmtHoursRaw(h)} ч`;

/** Работа других команд для строки таблицы запаса: та же роль и вид работ. */
export function itemsForRow(
  reserve: ReserveOut,
  role: string,
  workTypeId: string,
): OtherTeamWorkOut[] {
  return reserve.other_team_work.filter((item) => item.role === role && item.work_type_id === workTypeId);
}

/** Роль с видами работ, прошедшими фильтр {@link visibleReserveRows}. */
export interface VisibleReserveRole {
  role: string;
  role_label: string;
  rows: ReserveTypeRow[];
}

/** Часы, реально занятые из запаса вида работ: заблокировано + работа других команд. */
export function usedHours(row: ReserveTypeRow): number {
  return row.blocked_hours + row.other_teams_hours;
}

/**
 * Роли и виды работ с расходом с датой (заблокированные периоды или работа других команд) —
 * то, что показывает развёрнутая сводка. Виды без расхода и роли, у которых таких видов
 * не осталось, отбрасываются целиком.
 */
export function visibleReserveRows(reserve: ReserveOut | null | undefined): VisibleReserveRole[] {
  if (!reserve) return [];
  return reserve.roles
    .map((r) => ({ role: r.role, role_label: r.role_label, rows: r.rows.filter((row) => usedHours(row) > 0.05) }))
    .filter((r) => r.rows.length > 0);
}

/** Доля занятого от заложенного для полоски «Занято», 0..100. Заложено 0, но занято есть — 100. */
export function usagePct(row: ReserveTypeRow): number {
  const used = usedHours(row);
  if (row.planned_hours <= 0) return used > 0 ? 100 : 0;
  return Math.min(100, (used / row.planned_hours) * 100);
}

/** Подпись источника расхода под полоской «Занято»: заблокировано / другие команды / оба. */
export function usageCaption(row: ReserveTypeRow, itemCount: number): string {
  const hasBlocked = row.blocked_hours > 0.05;
  const hasOther = row.other_teams_hours > 0.05;
  if (hasBlocked && hasOther) {
    return `заблокировано ${fmtHours(row.blocked_hours)} · другие команды ${fmtHours(row.other_teams_hours)}`;
  }
  if (hasOther) return `другие команды · ${itemCount} ${pluralTasks(itemCount)}`;
  if (hasBlocked) return 'заблокировано';
  return '';
}

/**
 * Локальные подмены вида работ (ключ — задача, `backlog_item_id`), которые уже подтверждены
 * пересчитанной диаграммой — сервер хранит вид работ на задачу, а не на пару задача+роль, так что
 * одной задачи, за которую отвечают люди двух ролей, достаточно одного совпадения. Список — что
 * можно убрать из локальных подмен.
 */
export function resolvedOverrideKeys(
  otherTeamWork: OtherTeamWorkOut[],
  localOverrides: Record<string, string | null>,
): string[] {
  const resolved: string[] = [];
  const seen = new Set<string>();
  for (const item of otherTeamWork) {
    const key = item.backlog_item_id;
    if (seen.has(key) || !(key in localOverrides)) continue;
    seen.add(key);
    const serverValue = item.is_manual ? item.work_type_id : null;
    if (serverValue === localOverrides[key]) {
      resolved.push(key);
    }
  }
  return resolved;
}
