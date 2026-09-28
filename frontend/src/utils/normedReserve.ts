import type { ReserveOut } from '../api/resourcePlanning';
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
