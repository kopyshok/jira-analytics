import type { BacklogChild, BacklogItemResponse, EstimateCandidate } from '../types/api';
import { filterOffPlan, type InPlanRow } from './inPlan';

/** Спорная оценка — у роли заполнено несколько полей Jira с разными значениями,
 *  и пользователь ещё не выбрал, какое из них действует. */
export const hasDispute = (r: Pick<BacklogChild, 'disputed_roles'>) =>
  (r.disputed_roles?.length ?? 0) > 0;

/** Только спорные задачи: у строки остаются лишь спорные дочерние строки;
 *  строка без спора остаётся, только если под ней есть спорные. */
export function filterDisputed(
  rows: BacklogItemResponse[] | undefined,
): BacklogItemResponse[] | undefined {
  return rows?.flatMap((r) => {
    const kids = (r.children ?? []).filter(hasDispute);
    return hasDispute(r) || kids.length ? [{ ...r, children: kids }] : [];
  });
}

/** Метки «Только спорные» и «Не в плане» вместе оставляют задачи, подходящие под обе.
 *  Сначала спорные: иначе спорный родитель в плане, оставленный ради дочки
 *  «не в плане» без спора, остался бы в списке один. */
export function filterBacklogRows(
  rows: BacklogItemResponse[] | undefined,
  { onlyDisputed, onlyOffPlan }: { onlyDisputed: boolean; onlyOffPlan: boolean },
  offPlan: (r: InPlanRow) => boolean,
): BacklogItemResponse[] | undefined {
  const disputed = onlyDisputed ? filterDisputed(rows) : rows;
  return onlyOffPlan ? filterOffPlan(disputed, offPlan) : disputed;
}

/** Сколько спорных задач: строки и их дочерние строки. */
export function countDisputed(rows: BacklogItemResponse[] | undefined): number {
  return (rows ?? []).reduce(
    (n, r) => n + (hasDispute(r) ? 1 : 0) + (r.children ?? []).filter(hasDispute).length,
    0,
  );
}

/** Вариант «Ввести своё» в выборе. У полей Jira такого кода не бывает. */
export const MANUAL_CHOICE = '__manual__';

const sameHours = (a: number, b: number) => Math.abs(a - b) < 1e-6;

/** Что отметить в выборе — значение, которое действует сейчас. Совпало с полем
 *  Jira — это поле; не совпало ни с одним — действует ручная правка, отмечаем
 *  «своё» с её значением; значения нет — первое поле. «Принять» без изменений
 *  не меняет число в строке. */
export function defaultChoice(
  candidates: EstimateCandidate[],
  current: number | null | undefined,
): { picked: string; manual: number | null } {
  if (current == null) return { picked: candidates[0]?.source ?? MANUAL_CHOICE, manual: null };
  const same = candidates.find((c) => sameHours(c.value, current));
  return same ? { picked: same.source, manual: null } : { picked: MANUAL_CHOICE, manual: current };
}

/** Часы варианта: целые — без дробной части, иначе до сотых. */
export const formatChoiceHours = (v: number) => String(Math.round(v * 100) / 100);
