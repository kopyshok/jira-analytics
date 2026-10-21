import { useMemo, useState } from 'react';
import { App } from 'antd';
import type { ConflictOut } from '../../api/resourcePlanning';
import { usePatchConflict } from '../../hooks/useResourcePlanning';

export type ConflictGroupBy = 'item' | 'employee' | 'type';

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

/** Конфликт «живой» (не хранится) — статус у него не меняется. */
export const isLiveConflict = (c: ConflictOut) => !!c.is_live || c.id.startsWith('live:');

/** Активные и погашенные конфликты (без информационных); видимые — с погашенными или без. */
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

/**
 * Состояние панели конфликтов плана: что активно, что погашено, группировка и
 * смена статуса. Общее для раскладки Aurora и обложек.
 */
export function useConflictBoard(conflicts: ConflictOut[], planId: string | null) {
  const { message } = App.useApp();
  const patchMutation = usePatchConflict(planId);
  const [showHidden, setShowHidden] = useState(false);
  const [groupBy, setGroupBy] = useState<ConflictGroupBy>('item');

  const { active, hidden, visible } = useMemo(
    () => splitConflicts(conflicts, showHidden),
    [conflicts, showHidden],
  );

  const groups = useMemo(() => groupConflicts(visible, groupBy), [visible, groupBy]);

  const criticals = active.filter(c => c.severity === 'critical');
  const warnings = active.filter(c => c.severity === 'warning');

  const handleStatusChange = (conflictId: string, status: ConflictOut['status']) => {
    patchMutation.mutate(
      { conflictId, status },
      {
        onSuccess: () => message.success(`Статус: ${CONFLICT_STATUS_LABEL[status]}`),
        onError: () => message.error('Ошибка изменения статуса'),
      }
    );
  };

  return {
    showHidden, setShowHidden, groupBy, setGroupBy,
    active, hidden, visible, groups, criticals, warnings, handleStatusChange,
  };
}
