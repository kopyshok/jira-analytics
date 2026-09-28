import type { OtherTeamWorkOut, ReserveOut } from '../api/resourcePlanning';
import { fmtHours as fmtHoursRaw } from './rpBusy';

/** Сколько строк запаса в перерасходе (для красной подсветки и счётчика). */
export function overuseCount(reserve: ReserveOut | null | undefined): number {
  if (!reserve) return 0;
  return reserve.roles.reduce((n, r) => n + r.rows.filter((x) => x.overuse_hours > 0.5).length, 0);
}

/** Склонение «вид работ»: 1 вид, 2 вида, 5 видов. */
function pluralWorkTypes(n: number): string {
  if (n % 100 >= 11 && n % 100 <= 14) return 'видов';
  const last = n % 10;
  if (last === 1) return 'вид';
  if (last >= 2 && last <= 4) return 'вида';
  return 'видов';
}

/** Короткая красная подпись для шапки: «перерасход: 2 вида работ». Нет перерасхода — null. */
export function overuseLabel(reserve: ReserveOut | null | undefined): string | null {
  const n = overuseCount(reserve);
  if (n === 0) return null;
  return `перерасход: ${n} ${pluralWorkTypes(n)} работ`;
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
