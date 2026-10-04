import type { ReserveTypeRow, WatchMonthFree } from '../api/resourcePlanning';
import type { EmployeeResponse } from '../types/api';
import { fmtHours } from './normedReserve';
import { fmtHours as fmtNumber } from './rpBusy';

const RU_MONTHS_SHORT = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];

/**
 * «Вся роль в команде»: активные сотрудники роли ``role``, состоявшие в команде ``team``
 * хоть день квартала плана ``start`` — ``end`` (ISO, включительно). Без списка команд у
 * сотрудника — по его основной команде.
 */
export function roleTeamPicks(
  employees: EmployeeResponse[],
  team: string,
  role: string,
  start: string,
  end: string,
): string[] {
  if (!team || !role) return [];
  return employees
    .filter((e) => e.is_active && e.role === role)
    .filter((e) =>
      e.teams
        ? e.teams.some(
            // left_at — первый день вне команды.
            (t) => t.team === team && (!t.joined_at || t.joined_at <= end) && (!t.left_at || t.left_at > start),
          )
        : e.team === team,
    )
    .map((e) => e.id);
}

/**
 * Варианты окна «Подобрать людей»: активные сотрудники по ФИО. Люди плана и уже
 * наблюдаемые находятся поиском, но выбрать их нельзя — в подписи причина.
 */
export function watchPickerOptions(
  employees: EmployeeResponse[],
  inPlan: Set<string>,
  watched: Set<string>,
  roleLabel: Map<string, string>,
): { value: string; label: string; disabled: boolean }[] {
  return employees
    .filter((e) => e.is_active)
    .sort((a, b) => a.display_name.localeCompare(b.display_name, 'ru'))
    .map((e) => {
      const reason = inPlan.has(e.id) ? ' — уже в плане' : watched.has(e.id) ? ' — уже наблюдается' : '';
      const label = [e.display_name, e.role ? roleLabel.get(e.role) : undefined, e.team].filter(Boolean).join(' · ');
      return { value: e.id, label: label + reason, disabled: reason !== '' };
    });
}

/** «окт 40 · ноя 32 · дек 12» — свободные часы по месяцам квартала. */
export function freeByMonthLabel(months: WatchMonthFree[]): string {
  return months
    .map((m) => `${RU_MONTHS_SHORT[Number(m.month.slice(5, 7)) - 1]} ${fmtNumber(m.hours)}`)
    .join(' · ');
}

/** Остаток «Технических задач» основной команды: «осталось 20 ч» или «сверх запаса 30 ч». */
export function techReserveText(row: ReserveTypeRow | null | undefined): { text: string; over: boolean } {
  if (!row) return { text: '—', over: false };
  if (row.overuse_hours > 0.05) return { text: `сверх запаса ${fmtHours(row.overuse_hours)}`, over: true };
  return { text: `осталось ${fmtHours(row.remaining_hours)}`, over: false };
}
