export interface TourStepDef {
  /** Значение атрибута data-tour у элемента; null — окно по центру экрана. */
  target: string | null;
  title: string;
  description: string;
  /** data-tour элемента, по которому кликнуть перед шагом (переключить вкладку). */
  clickFirst?: string;
}

export interface TourDef {
  id: string;
  /** Куда перейти перед экскурсией; нет — остаться на текущей странице. */
  route?: string;
  steps: TourStepDef[];
}

const list: TourDef[] = [
  {
    id: 'categories',
    route: '/categories',
    steps: [
      { target: 'categories-waiting', title: 'Сколько ждёт разбора', description: 'Задачи команды без подтверждённой категории. Цель шага — оставить здесь не больше 10% задач.' },
      { target: 'categories-queues', title: 'Очереди', description: '«К разбору» — новые задачи из Jira. Остальные — уже разобранные: активные, инициативы, архив. Клик переключает очередь.' },
      { target: 'categories-table', title: 'Дерево задач', description: 'Проект → эпик → задача. Категория эпика наследуется задачами ниже.' },
      { target: 'categories-col-category', title: 'Категория', description: 'Выберите категорию — она применится к задаче и её потомкам. Задачи для планирования квартала относите к «Инициативы (на потом)» — они сами появятся в целевых задачах.' },
      { target: 'categories-bulk', title: 'Сразу несколько', description: 'Отметьте строки галочками и назначьте категорию всем разом.' },
    ],
  },
  {
    id: 'capacity-team',
    route: '/capacity',
    steps: [
      { target: 'capacity-tab-team', clickFirst: 'capacity-tab-team', title: 'Вкладка «Команда»', description: 'Состав команды на выбранный квартал и загрузка каждого.' },
      { target: 'capacity-add-employee', title: 'Добавить сотрудника', description: 'Поиск по имени или почте в Jira.' },
      { target: 'capacity-role', title: 'Роль', description: 'У сотрудника одна роль. От неё зависят участие в сценариях и правила загрузки — заполните у каждого.' },
      { target: 'capacity-team-table', title: 'Карточка сотрудника', description: 'Клик по строке открывает карточку: дата вступления в команду («В команде с…») и участие в других командах.' },
      { target: 'capacity-toolbar', title: 'Фильтры', description: 'Поиск сотрудника, факт и проценты, выключенные сотрудники.' },
    ],
  },
  {
    id: 'capacity-absences',
    route: '/capacity',
    steps: [
      { target: 'capacity-tab-absences', clickFirst: 'capacity-tab-absences', title: 'Вкладка «Отсутствия»', description: 'Отпуска, больничные, обучение — всё, что уменьшает ресурс команды.' },
      { target: 'capacity-absence-heatmap', title: 'Тепловая карта', description: 'Кто и когда отсутствует в квартале.' },
      { target: 'capacity-absence-bulk', title: 'Массовое добавление', description: 'Одно отсутствие сразу нескольким сотрудникам.' },
      { target: 'capacity-absence-table', title: 'По сотрудникам', description: 'В строке сотрудника — «добавить» отсутствие.' },
      { target: null, title: 'Готово?', description: 'Когда внесёте отсутствия на квартал — вернитесь в «Первые шаги» и нажмите «Проверил».' },
    ],
  },
  {
    id: 'backlog',
    route: '/backlog?view=active',
    steps: [
      { target: null, title: 'Откуда берутся целевые задачи', description: 'Автоматически из Jira — задачи, отнесённые при категоризации к «Инициативы (на потом)». И вручную — для идей, которых ещё нет в Jira.' },
      { target: 'backlog-tabs', title: 'Вкладки', description: '«Активные» — уже приняты в работу утверждённым сценарием. «Бэклог» — кандидаты на квартал, основная работа здесь. «Архив» — отложенные и отменённые.' },
      { target: 'backlog-manual-idea', title: 'Идея вручную', description: 'Черновик без задачи в Jira. Когда задача появится — свяжите её с идеей.' },
      { target: 'backlog-col-prio', title: 'Приоритет', description: 'Меньше число — выше приоритет. В сценарии инициативы идут в этом порядке.' },
      { target: 'backlog-col-roles', title: 'Оценки по ролям', description: 'Часы анализа, разработки, тестирования и ОПЭ. Клик по ячейке открывает редактор.' },
      { target: 'backlog-gear', title: 'Параметры планирования', description: 'Вовлечённость, длительность и параллельность по фазам — их использует ресурсное планирование.' },
      { target: 'backlog-col-inplan', title: '«В план»', description: 'Галочка включает инициативу в планирование.' },
    ],
  },
  {
    id: 'planning',
    route: '/planning',
    steps: [
      { target: 'planning-scenario-select', title: 'Сценарии команды', description: 'Сценарий — вариант плана квартала. Их может быть несколько, утверждается один.' },
      { target: 'planning-new-scenario', title: 'Новый сценарий', description: 'Квартал, год и команда — название подставится само. Правила прошлого квартала можно скопировать на вкладке «Правила».' },
      { target: 'planning-involvement', title: 'Вовлечённость', description: 'Вовлечённость по ролям команды и личные настройки сотрудников на квартал. Проверьте значения и отметьте подпункт в «Первых шагах».' },
      { target: 'planning-tab-rules', clickFirst: 'planning-tab-rules', title: 'Правила', description: 'Вкладка «Правила»: сопровождение, встречи, техдолг — доля времени роли в процентах. Правила прошлого квартала копируются кнопкой «Из сценария»; свои проценты сотрудника — в «Вовлечённости».' },
      { target: 'planning-rules-card', title: 'Правила обязательных работ', description: 'После «Сохранить» ресурс под инициативы пересчитается.' },
      { target: 'planning-capacity-panel', title: 'Ресурс команды', description: 'Доступно, обязательные работы и остаток под инициативы по ролям.' },
      { target: 'planning-approve', title: 'Утвердить', description: 'Когда план собран — утвердите сценарий. По утверждённому строится ресурсный план.' },
    ],
  },
  {
    id: 'resource-planning',
    route: '/resource-planning',
    steps: [
      { target: 'rp-scenario-select', title: 'Утверждённый сценарий', description: 'План строится по утверждённому сценарию команды.' },
      { target: 'rp-distribute', title: 'Распределить', description: 'Сервис раскладывает фазы инициатив по исполнителям и дням с учётом отсутствий и вовлечённости.' },
      { target: 'rp-view', title: 'Вид', description: 'По задачам или по исполнителям, масштаб шкалы и другие настройки показа.' },
      { target: 'rp-gantt', title: 'Диаграмма', description: 'Сроки фаз. Клик по полосе открывает подробности и ручную правку.' },
      { target: 'rp-load', title: 'Загрузка по дням', description: 'Перегруз сотрудников виден сразу.' },
    ],
  },
  {
    id: 'header',
    steps: [
      { target: 'header-team', title: 'Команда', description: 'Фильтр команды действует во всех разделах.' },
      { target: 'header-period', title: 'Период', description: 'Квартал или месяц для отчётов.' },
      { target: 'header-help', title: 'Справка', description: 'Справка по текущему разделу и лента «Что нового».' },
      { target: 'header-onboarding', title: 'Первые шаги', description: 'Сюда можно вернуться в любой момент.' },
    ],
  },
  {
    id: 'dashboard',
    route: '/',
    steps: [
      { target: 'dash-projects', title: 'Проекты квартала', description: 'Над чем команда работает в периоде.' },
      { target: 'dash-normed', title: 'Нормированные работы', description: 'План и факт по ролям.' },
      { target: 'dash-worklogs', title: 'Ворклоги по категориям', description: 'Куда ушли часы команды.' },
      { target: 'dash-balance', title: 'Баланс часов', description: 'Списано против нормы.' },
    ],
  },
  {
    id: 'analytics',
    route: '/analytics',
    steps: [
      { target: 'analytics-period', title: 'Уточнить период', description: 'Даты внутри периода из шапки.' },
      { target: 'analytics-hierarchy', title: 'Иерархия', description: 'Задачи деревом до самого верхнего родителя.' },
      { target: 'analytics-settings', title: 'Настройка отчёта', description: 'Какие уровни группировки и колонки показывать.' },
      { target: 'analytics-filters', title: 'Фильтры', description: 'Сотрудник, вид работ, категория, поиск задачи.' },
      { target: 'analytics-table', title: 'Отчёт', description: 'Команда → роль → сотрудник → вид работ → категория → задача.' },
    ],
  },
  {
    id: 'team-desk',
    route: '/team-desk',
    steps: [
      { target: 'desk-filters', title: 'Фильтры', description: 'Команды, разработчики, режим среза, период, спринт и релиз.' },
      { target: 'desk-tabs', title: 'Раскладки', description: 'Светофор, ведомость, проблемы вперёд.' },
      { target: 'desk-flags', title: 'Замечания', description: 'Зависшие и перерасходованные задачи, счётчики по статусам.' },
      { target: 'desk-issues', title: 'Задачи', description: 'Сгруппированы по разработчикам.' },
    ],
  },
];

export const TOURS: Record<string, TourDef> = Object.fromEntries(list.map(t => [t.id, t]));
