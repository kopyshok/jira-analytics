// Каталог виджетов рабочего стола аналитика: ключ → русская подпись.
// Порядок соответствует порядку отображения по умолчанию на бэкенде
// (app/services/work_desk_widgets.py — WIDGET_KEYS).

export interface WidgetCatalogItem {
  key: string;
  label: string;
}

export const WIDGET_CATALOG: WidgetCatalogItem[] = [
  { key: 'my_tasks', label: 'Мои проекты' },
  { key: 'my_timeline', label: 'Таймлайн моих проектов' },
  { key: 'hours_balance', label: 'Переработка' },
  { key: 'category_breakdown', label: 'Часы по видам работ' },
  { key: 'team_absences', label: 'Отсутствия команды' },
  { key: 'team_availability', label: 'Занятость команды' },
  { key: 'production_calendar', label: 'Производственный календарь' },
  { key: 'awaiting_reaction', label: 'Ждут моей реакции' },
];

export const WIDGET_LABELS: Record<string, string> = Object.fromEntries(
  WIDGET_CATALOG.map((w) => [w.key, w.label]),
);
