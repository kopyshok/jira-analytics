import type { ConflictOut } from '../api/resourcePlanning';

/** Подписи типов конфликтов плана — общие для панели конфликтов во всех раскладках. */
export const CONFLICT_TYPE_LABELS: Record<string, string> = {
  OVERLOAD_HIGH: 'Сильная перегрузка',
  OVERLOAD_MED: 'Средняя перегрузка',
  OVERLOAD_LIGHT: 'Лёгкая перегрузка',
  QUARTER_OVERFLOW: 'Не вмещается в квартал',
  SPLIT_REQUIRED: 'Требуется разбивка',
  NO_ANALYST: 'Нет аналитика',
  NO_DEV: 'Нет разработчика',
  LATE_START: 'Поздний старт',
  OUT_OF_TEAM: 'Вне команды',
  CROSS_TEAM_OVERLAP: 'Пересечение с другой командой',
  PREDECESSOR_VIOLATED: 'Нарушен порядок предшественников',
  LEVELING_DELAY: 'Сдвиг при выравнивании',
  LEVELING_REASSIGN: 'Переназначение',
  UNPLACED_HOURS: 'Часы не размещены',
  NORMED_OVERUSE: 'Перерасход нормированных работ',
  NORMED_UNPLACED: 'Квартал не вмещается',
};

export const CONFLICT_STATUS_LABEL: Record<ConflictOut['status'], string> = {
  open: 'Открыт',
  acknowledged: 'Принят',
  muted: 'Замучен',
  resolved: 'Решён',
};

export type ConflictGroupBy = 'item' | 'employee' | 'type';

/** «Живой» конфликт не хранится — статус у него не меняется, сервер ответит отказом. */
export const isLiveConflict = (c: ConflictOut): boolean => !!c.is_live || c.id.startsWith('live:');

/**
 * Конфликты для показа: без информационных; погашенные (заглушенные и решённые)
 * отдельно — их показывают по запросу.
 */
export function splitConflicts(conflicts: ConflictOut[], showHidden: boolean) {
  const nonInfo = conflicts.filter(c => c.severity !== 'info');
  const active = nonInfo.filter(c => c.status !== 'muted' && c.status !== 'resolved');
  const hidden = nonInfo.filter(c => c.status === 'muted' || c.status === 'resolved');
  return { active, hidden, visible: showHidden ? [...active, ...hidden] : active };
}

/** Группы конфликтов по задаче, сотруднику или типу — по алфавиту подписи. */
export function groupConflicts(visible: ConflictOut[], groupBy: ConflictGroupBy) {
  const map = new Map<string, { label: string; items: ConflictOut[] }>();
  for (const c of visible) {
    let key = 'misc';
    let label = '—';
    if (groupBy === 'item') {
      key = c.backlog_item_id ?? 'misc';
      label = c.backlog_item_title ?? 'Без инициативы';
    } else if (groupBy === 'employee') {
      key = c.employee_id ?? 'misc';
      label = c.employee_id
        ? c.employee_name ?? c.employee_id
        : 'Без сотрудника';
    } else {
      // Незнакомые типы (сервер новее фронта) — одной группой «Прочее»,
      // без служебного кода в подписи.
      key = CONFLICT_TYPE_LABELS[c.type] ? c.type : 'misc';
      label = CONFLICT_TYPE_LABELS[c.type] ?? 'Прочее';
    }
    if (!map.has(key)) map.set(key, { label, items: [] });
    map.get(key)!.items.push(c);
  }
  return [...map.entries()]
    .map(([key, v]) => ({ key, label: v.label, items: v.items }))
    .sort((a, b) => a.label.localeCompare(b.label, 'ru'));
}
