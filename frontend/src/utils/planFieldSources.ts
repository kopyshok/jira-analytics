/** Настройка «Плановые трудозатраты»: несколько полей Jira на роль.
 *  Формат совпадает с сервером (app/services/plan_sources.py): JSON-список
 *  `[{field_id, kind, name}]` по порядку или старое значение — одно поле строкой. */
export type PlanFieldKind = 'alt' | 'sum';

export interface PlanFieldEntry {
  field_id: string;
  kind: PlanFieldKind;
  name?: string | null;
}

/** Старая строка — одно поле-альтернатива; мусор и повторы пропускаются, как на сервере. */
export function parsePlanFieldSetting(raw: string | null | undefined): PlanFieldEntry[] {
  const text = (raw ?? '').trim();
  if (!text) return [];
  if (!text.startsWith('[')) return [{ field_id: text, kind: 'alt', name: null }];
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    return [];
  }
  if (!Array.isArray(data)) return [];
  const seen = new Set<string>();
  return data.flatMap((e): PlanFieldEntry[] => {
    if (!e || typeof e !== 'object') return [];
    const o = e as Record<string, unknown>;
    const id = typeof o.field_id === 'string' ? o.field_id.trim() : '';
    if (!id || seen.has(id)) return [];
    seen.add(id);
    return [{
      field_id: id,
      kind: o.kind === 'sum' ? 'sum' : 'alt',
      name: typeof o.name === 'string' && o.name.trim() ? o.name : null,
    }];
  });
}

/** Значение настройки: пустые строки и повторы не пишем; ничего не выбрано — пустая строка. */
export function serializePlanFieldSetting(entries: PlanFieldEntry[]): string {
  const seen = new Set<string>();
  const clean = entries.flatMap((e) => {
    const id = e.field_id.trim();
    if (!id || seen.has(id)) return [];
    seen.add(id);
    return [{ field_id: id, kind: e.kind, ...(e.name ? { name: e.name } : {}) }];
  });
  return clean.length ? JSON.stringify(clean) : '';
}

/** Что читает синк: поля и их вид по порядку. Название — только подпись. */
const fieldLayout = (raw: string) =>
  JSON.stringify(parsePlanFieldSetting(raw).map((e) => [e.field_id, e.kind]));

/** Значение настройки после правки. Те же поля с тем же видом по порядку —
 *  исходная строка как есть: правка без изменений («Добавить поле» и корзина,
 *  ↑ и ↓) не должна переписывать старую строку списком — сервер счёл бы это
 *  сменой полей и перечитал бы все задачи из Jira. */
export function nextPlanFieldSetting(initial: string, entries: PlanFieldEntry[]): string {
  const next = serializePlanFieldSetting(entries);
  return fieldLayout(next) === fieldLayout(initial) ? initial : next;
}

export function moveEntry<T>(list: T[], index: number, delta: -1 | 1): T[] {
  const target = index + delta;
  if (target < 0 || target >= list.length) return list;
  const next = list.slice();
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

/** Номер поля для приглушённой подписи рядом с названием: «12431» вместо «customfield_12431». */
export const fieldIdHint = (fieldId: string) => fieldId.replace(/^customfield_/, '');
