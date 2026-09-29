import type { OnboardingStatus } from '../api/onboarding';

export interface SetupStep {
  /** id шага на сервере; у группы — свой id, на сервере его нет. */
  id: string;
  title: string;
  hint: string;
  /** Куда ведёт «Перейти». */
  route?: string;
  /** Какую экскурсию запускает «Показать». */
  tourId?: string;
  /** Ручной шаг отмечается кнопкой «Проверил». */
  manual?: boolean;
  /** id ролика-инструкции (см. help-videos/videos.ts) — включает кнопку «Видео». */
  videoId?: string;
  /** Подпункты: шаг закрыт, когда закрыты все. */
  children?: SetupStep[];
}

export interface IntroStep {
  tourId: string;
  title: string;
  hint: string;
}

export const SETUP_STEPS: SetupStep[] = [
  {
    id: 'issues_loaded',
    title: 'Задачи команды загружены из Jira',
    hint: 'Синхронизация общая и идёт по расписанию. Если задач команды нет — обратитесь к администратору.',
    route: '/sync',
  },
  {
    id: 'categorization',
    title: 'Категоризация задач',
    hint: 'Разберите задачи команды по категориям: от категории зависит, куда пойдут часы в отчётах и что попадёт в целевые задачи. Шаг выполнен, когда неразобранных осталось не больше 10%.',
    route: '/categories',
    tourId: 'categories',
    videoId: 'categorize-issue',
  },
  {
    id: 'team_roles',
    title: 'Состав команды и роли',
    hint: 'Проверьте участников и заполните роль у каждого — от роли зависят сценарии и правила загрузки. Дата вступления в команду — в карточке сотрудника.',
    route: '/capacity',
    tourId: 'capacity-team',
    videoId: 'team-member-add',
  },
  {
    id: 'absences',
    title: 'Отсутствия',
    hint: 'Внесите отпуска, больничные и обучение на квартал. Сервис не отличит «отпусков нет» от «не внесли», поэтому отметьте шаг сами.',
    route: '/capacity',
    tourId: 'capacity-absences',
    manual: true,
    videoId: 'absence-add',
  },
  {
    id: 'backlog',
    title: 'Целевые задачи (бэклог)',
    hint: 'Наполняются автоматически из Jira — задачи, отнесённые при категоризации к «Инициативы (на потом)», — и вручную кнопкой «Идея вручную» для идей, которых ещё нет в Jira. Дальше: приоритеты, оценки по ролям, параметры планирования (шестерёнка).',
    route: '/backlog?view=active',
    tourId: 'backlog',
    videoId: 'backlog-idea-add',
  },
  {
    id: 'scenario',
    title: 'Сценарий квартала',
    hint: 'Сценарий собирает инициативы квартала под ресурс команды.',
    route: '/planning',
    tourId: 'planning',
    videoId: 'scenario-create',
    children: [
      { id: 'scenario_created', title: 'Сценарий создан', hint: 'Кнопка «Новый сценарий».' },
      {
        id: 'scenario_rules',
        title: 'Нормированные работы проверены',
        hint: 'Вкладка «Правила»: доля времени ролей на сопровождение, встречи, техдолг.',
        manual: true,
      },
      {
        id: 'scenario_involvement',
        title: 'Вовлечённость проверена',
        hint: 'Кнопка «Вовлечённость»: значения по ролям на квартал.',
        manual: true,
      },
    ],
  },
  {
    id: 'resource_plan',
    title: 'Ресурсное планирование',
    hint: 'Выберите утверждённый сценарий и нажмите «Распределить»: сервис разложит фазы по исполнителям и дням.',
    route: '/resource-planning',
    tourId: 'resource-planning',
    videoId: 'resource-plan-build',
  },
];

export const INTRO_STEPS: IntroStep[] = [
  { tourId: 'header', title: 'Шапка: команда, период, справка', hint: 'Что настраивается один раз и действует во всех разделах.' },
  { tourId: 'dashboard', title: 'Дашборд', hint: 'Сводка команды за период.' },
  { tourId: 'analytics', title: 'Аналитика', hint: 'Отчёт по часам: команда → роль → сотрудник → категория → задача.' },
  { tourId: 'team-desk', title: 'Стол тимлида', hint: 'Задачи разработчиков: что зависло, что перерасходовано.' },
];

/** Шаг закрыт: выполнен или пропущен. Группа — когда закрыты все подпункты. */
export function isClosed(step: SetupStep, status: OnboardingStatus | undefined): boolean {
  if (step.children) return step.children.every(c => isClosed(c, status));
  const state = status?.steps[step.id]?.state;
  return state === 'done' || state === 'skipped';
}

/** Прогресс для кнопки в шапке: закрытые шаги верхнего уровня обоих блоков. */
export function progress(status: OnboardingStatus | undefined, hasTeam: boolean) {
  const tours = new Set(status?.me.completed_tours ?? []);
  const introDone = INTRO_STEPS.filter(s => tours.has(s.tourId)).length;
  const setupDone = hasTeam ? SETUP_STEPS.filter(s => isClosed(s, status)).length : 0;
  const total = INTRO_STEPS.length + (hasTeam ? SETUP_STEPS.length : 0);
  return { done: introDone + setupDone, total };
}
