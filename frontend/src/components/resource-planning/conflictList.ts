import { useMemo, useState } from 'react';
import { App } from 'antd';
import type { ConflictOut } from '../../api/resourcePlanning';
import { usePatchConflict } from '../../hooks/useResourcePlanning';

export type ConflictGroupBy = 'item' | 'employee' | 'type';
type GroupBy = ConflictGroupBy;

export const TYPE_LABELS: Record<string, string> = {
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

export const STATUS_LABEL: Record<ConflictOut['status'], string> = {
  open: 'Открыт',
  acknowledged: 'Принят',
  muted: 'Замучен',
  resolved: 'Решён',
};

/** Состояние списка конфликтов: группировка, погашенные, смена статуса.
 *  Общее для панели Aurora и полосы конфликтов в раскладке скина. */
export function useConflictList(conflicts: ConflictOut[], planId: string | null) {
  const { message } = App.useApp();
  const patchMutation = usePatchConflict(planId);
  const [showHidden, setShowHidden] = useState(false);
  const [groupBy, setGroupBy] = useState<GroupBy>('item');

  const { active, hidden, visible } = useMemo(() => {
    const nonInfo = conflicts.filter(c => c.severity !== 'info');
    const a = nonInfo.filter(c => c.status !== 'muted' && c.status !== 'resolved');
    const h = nonInfo.filter(c => c.status === 'muted' || c.status === 'resolved');
    return { active: a, hidden: h, visible: showHidden ? [...a, ...h] : a };
  }, [conflicts, showHidden]);

  const groups = useMemo(() => {
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
        key = TYPE_LABELS[c.type] ? c.type : 'misc';
        label = TYPE_LABELS[c.type] ?? 'Прочее';
      }
      if (!map.has(key)) map.set(key, { label, items: [] });
      map.get(key)!.items.push(c);
    }
    return [...map.entries()]
      .map(([key, v]) => ({ key, label: v.label, items: v.items }))
      .sort((a, b) => a.label.localeCompare(b.label, 'ru'));
  }, [visible, groupBy]);

  const criticals = active.filter(c => c.severity === 'critical');
  const warnings = active.filter(c => c.severity === 'warning');

  const handleStatusChange = (conflictId: string, status: ConflictOut['status']) => {
    patchMutation.mutate(
      { conflictId, status },
      {
        onSuccess: () => message.success(`Статус: ${STATUS_LABEL[status]}`),
        onError: () => message.error('Ошибка изменения статуса'),
      }
    );
  };

  return { showHidden, setShowHidden, groupBy, setGroupBy, active, hidden, groups, criticals, warnings, handleStatusChange };
}

