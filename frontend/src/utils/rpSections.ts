import type { AssignmentOut } from '../api/resourcePlanning';

/** Группа инициативы: своя группа работы, иначе группа главного исполнителя
 *  из сценария — сервер уже кладёт её в subgroup_id назначения (та же
 *  логика, что в Сценариях), фронту достаточно взять имя по id. */
export function buildSectionByItem(
  assignments: AssignmentOut[],
  subgroupNameById: Map<string, string>,
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const a of assignments) {
    if (a.backlog_item_id in out) continue;
    out[a.backlog_item_id] = (a.subgroup_id && subgroupNameById.get(a.subgroup_id)) || '';
  }
  return out;
}

/** Инициативы одной группы идут подряд; порядок групп — как в реестре
 *  команды, «без группы» в конце. Внутри секции порядок не меняется. */
export function sortBySection(
  assignments: AssignmentOut[],
  sectionByItem: Record<string, string>,
  subgroupOrder: string[],
): AssignmentOut[] {
  const rank = new Map(subgroupOrder.map((name, i) => [name, i]));
  const rankOf = (itemId: string) => {
    const name = sectionByItem[itemId] ?? '';
    return name ? (rank.get(name) ?? subgroupOrder.length) : subgroupOrder.length + 1;
  };
  return [...assignments].sort(
    (a, b) => rankOf(a.backlog_item_id) - rankOf(b.backlog_item_id),
  );
}
