export const PATH_LABELS: Record<string, string> = {
  '/': 'Дашборд',
  '/projects': 'Проекты',
  '/projects/:key': 'Карточка проекта',
  '/analytics': 'Аналитика',
  '/analytics/work-type-report': 'Отчёт по видам работ',
  '/analytics/work-type-report/print': 'Отчёт по видам работ (печать)',
  '/executive': 'Сводка для руководства',
  '/sync': 'Синхронизация',
  '/categories': 'Категории',
  '/capacity': 'Загрузка',
  '/backlog': 'Бэклог',
  '/planning': 'Планирование',
  '/resource-planning': 'Планирование ресурсов',
  '/resource-planning/compare': 'Сравнение сценариев',
  '/settings': 'Настройки',
  '/feedback': 'Обратная связь',
  '/login': 'Логин',
};

export const pathLabel = (path: string): string => PATH_LABELS[path] ?? path;
