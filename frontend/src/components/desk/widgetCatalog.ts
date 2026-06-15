// Каталог виджетов рабочего стола аналитика: ключ → русская подпись.
// Порядок соответствует порядку отображения по умолчанию на бэкенде
// (app/services/work_desk_widgets.py — WIDGET_KEYS).

export interface WidgetCatalogItem {
  key: string;
  label: string;
}

export const WIDGET_CATALOG: WidgetCatalogItem[] = [
  { key: 'my_tasks', label: 'Мои задачи и плановые даты' },
  { key: 'weekly_load', label: 'Загрузка по месяцам' },
  { key: 'my_conflicts', label: 'Конфликты планирования' },
  { key: 'hours_balance', label: 'Баланс часов' },
  { key: 'unlogged_days', label: 'Несписанное время' },
  { key: 'category_breakdown', label: 'Виды работ' },
  { key: 'team_absences', label: 'Отсутствия коллег' },
  { key: 'team_availability', label: 'Доступность команды' },
  { key: 'production_calendar', label: 'Производственный календарь' },
  { key: 'quarter_deadlines', label: 'Дедлайны квартала' },
  { key: 'external_help', label: 'Помощь извне' },
  { key: 'recent_changes', label: 'Изменения в планах' },
];

export const WIDGET_LABELS: Record<string, string> = Object.fromEntries(
  WIDGET_CATALOG.map((w) => [w.key, w.label]),
);
