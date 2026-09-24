import type { QueryKey } from '@tanstack/react-query';
import type { AssignmentCandidate, AssignmentCandidateGroup, AssignmentOut } from '../api/resourcePlanning';

const ddmm = (iso: string) => `${iso.slice(8, 10)}.${iso.slice(5, 7)}`;

/** Ключ списка кандидатов фазы: план, строка фазы, её задача и фаза. */
export const candidatesQueryKey = (
  planId: string | null,
  a: Pick<AssignmentOut, 'id' | 'backlog_item_id' | 'phase'> | null,
) => ['assignment-candidates', planId, a?.id ?? null, a?.backlog_item_id ?? null, a?.phase ?? null] as const;

/** Пока грузится список кандидатов, прежний подставляем, только если он той же фазы
 *  той же задачи того же плана: пересчёт пересоздаёт строку фазы с новым id, а кандидаты
 *  у неё те же. Список другой фазы или задачи не подставляем — мелькнула бы чужая
 *  группа «Из Jira». */
export function sameCandidatesTarget(prev: QueryKey, next: QueryKey): boolean {
  const [, plan, , item, phase] = prev;
  const [, nextPlan, , nextItem, nextPhase] = next;
  return plan === nextPlan && item === nextItem && phase === nextPhase;
}

/**
 * «Имя · Роль · Команда · 42%»; у своей команды — без команды, с границами участия.
 * Роль — подпись из справочника ролей; служебный код без подписи не показываем.
 */
export function candidateLabel(
  e: AssignmentCandidate,
  groupKey: AssignmentCandidateGroup['key'],
  roleLabels: ReadonlyMap<string, string>,
): string {
  const parts = [e.display_name];
  const role = e.role ? roleLabels.get(e.role) : undefined;
  if (role) parts.push(role);
  if (groupKey !== 'team' && e.team) parts.push(e.team);
  parts.push(`${Math.round(e.load_pct)}%`);
  let label = parts.join(' · ');
  if (groupKey === 'team') {
    if (e.member_from && e.member_to) label += ` (в команде ${ddmm(e.member_from)}–${ddmm(e.member_to)})`;
    else if (e.member_to) label += ` (в команде по ${ddmm(e.member_to)})`;
    else if (e.member_from) label += ` (в команде с ${ddmm(e.member_from)})`;
  }
  return label;
}

/** Группы опций для AntD Select. */
export function candidateOptions(
  groups: AssignmentCandidateGroup[],
  roleLabels: ReadonlyMap<string, string>,
) {
  return groups.map((g) => ({
    label: g.label,
    title: g.label,
    options: g.employees.map((e) => ({ value: e.employee_id, label: candidateLabel(e, g.key, roleLabels) })),
  }));
}
