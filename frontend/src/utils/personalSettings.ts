import type { PersonalNormedItem } from '../types/api';

/** «Q4 2026» — квартал, с которого действует запись. */
export function formatQuarter(year: number, quarter: number): string {
  return `Q${quarter} ${year}`;
}

/** «100%» или «—» (вовлечённость не задана — действует обычный порядок). */
export function formatInvolvement(involvement: number | null): string {
  return involvement == null ? '—' : `${Math.round(involvement * 100)}%`;
}

/**
 * Текст ячейки «Нормированные работы»: «по правилам роли» — normed_custom=false;
 * «нет» — свои проценты, но список пуст; иначе — виды и проценты через точку.
 */
export function formatNormed(row: { normed_custom: boolean; normed: PersonalNormedItem[] }): string {
  if (!row.normed_custom) return 'по правилам роли';
  if (row.normed.length === 0) return 'нет';
  return row.normed.map((n) => `${n.label} ${n.percent_of_norm}%`).join(' · ');
}

/** Сумма процентов «своих» нормированных работ — для предупреждения о превышении 100%. */
export function sumPercent(items: { percent_of_norm: number }[]): number {
  return items.reduce((s, i) => s + (i.percent_of_norm || 0), 0);
}

/**
 * Проценты правил сценария для роли сотрудника (вид работ → %) — подстановка при
 * переключении на «свои». Правила самой роли, если есть хоть одно, иначе — правила
 * «для всех ролей» (та же логика, что на сервере в `normed_reserve.team_reserve`).
 * Учитываются только виды работ, уменьшающие запас (`poolWorkTypeIds`) — и при
 * решении, есть ли у роли свои правила, и в самой сумме; правила одного вида
 * работ складываются, а не перезаписывают друг друга (тоже как на сервере).
 */
export function roleNormedPercents(
  rules: { role: string | null; work_type_id: string; percent_of_norm: number }[],
  role: string | null,
  poolWorkTypeIds: Iterable<string>,
): Record<string, number> {
  const poolIds = new Set(poolWorkTypeIds);
  const pool = rules.filter((r) => poolIds.has(r.work_type_id));
  const forRole = role ? pool.filter((r) => r.role === role) : [];
  const chosen = forRole.length > 0 ? forRole : pool.filter((r) => r.role === null);
  const map: Record<string, number> = {};
  for (const r of chosen) map[r.work_type_id] = (map[r.work_type_id] ?? 0) + r.percent_of_norm;
  return map;
}
