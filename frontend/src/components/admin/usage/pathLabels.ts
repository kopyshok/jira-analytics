export const PATH_LABELS: Record<string, string> = {
  '/dashboard': 'Дашборд',
  '/analytics': 'Аналитика',
  '/projects': 'Проекты',
  '/projects/:key': 'Карточка проекта',
  '/sync': 'Синхронизация',
  '/categories': 'Категории',
  '/category-config': 'Настройка категорий',
  '/capacity': 'Загрузка',
  '/backlog': 'Бэклог',
  '/planning': 'Планирование',
  '/scenarios/:id': 'Сценарий',
  '/scenarios/:id/edit': 'Редактор сценария',
  '/resource-planning': 'Планирование ресурсов',
  '/executive': 'Сводка для руководства',
  '/themes': 'Темы',
  '/work-type-report': 'Отчёт по видам работ',
  '/feedback': 'Обратная связь',
  '/settings': 'Настройки',
  '/login': 'Логин',
};

export const pathLabel = (path: string): string => PATH_LABELS[path] ?? path;
