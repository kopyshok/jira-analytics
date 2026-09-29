export interface VideoInfo {
  title: string;
  src: string;
  poster: string;
}

const BASE = `${import.meta.env.BASE_URL}help-videos/`;

const video = (id: string, title: string): [string, VideoInfo] => [
  id,
  { title, src: `${BASE}${id}.webm`, poster: `${BASE}${id}.jpg` },
];

/** Реестр роликов-инструкций: id → название, файл, обложка. */
export const VIDEOS: Record<string, VideoInfo> = Object.fromEntries([
  // Общее, Дашборд, Проекты
  video('start-header', 'Как начать: команда, период, справка'),
  video('dashboard-overview', 'Как провести утренний обзор команды'),
  video('projects-portfolio', 'Как посмотреть портфель квартала и план проекта'),
  // Категории задач, Аналитика
  video('categorize-issue', 'Как разобрать новые задачи'),
  video('category-to-scenario', 'Как инициатива попадает в сценарий'),
  video('analytics-employee-hours', 'Как посмотреть, куда ушли часы сотрудника'),
  video('analytics-categorize', 'Как разобрать часы без категории прямо из отчёта'),
  // Ресурсы
  video('team-member-add', 'Как добавить сотрудника в команду'),
  video('absence-add', 'Как внести отпуск и увидеть сдвиг плана'),
  video('employee-transfer', 'Как перевести сотрудника в другую группу'),
  video('capacity-roles-desks', 'Как настроить роли и рабочий стол аналитика'),
  // Целевые задачи
  video('backlog-idea-add', 'Как завести идею и связать её с Jira'),
  video('backlog-planning-params', 'Как задать параметры планирования'),
  video('backlog-quarter-selection', 'Как отобрать задачи к кварталу'),
  // Сценарии
  video('scenario-create', 'Как собрать сценарий квартала'),
  video('scenario-rules', 'Как задать нормированные работы и вовлечённость'),
  video('scenario-approve', 'Как утвердить сценарий и что дальше'),
  video('scenario-developer', 'Как назначить разработчика в сценарии'),
  video('scenario-review', 'Как пересмотреть сценарий в середине квартала'),
  video('scenario-groups', 'Как вести сценарий команды с группами'),
  // Ресурсное планирование
  video('resource-plan-build', 'Как построить ресурсный план и прочитать его'),
  video('rp-conflicts', 'Как разобрать перегрузки в плане'),
  video('rp-executor', 'Как сменить исполнителя, дату и вовлечённость фазы'),
  video('rp-split', 'Как разбить фазу на двоих'),
  video('rp-blocked-periods', 'Как заблокировать период'),
  video('rp-groups-cross-team', 'Как видеть группы и людей из других команд'),
  video('rp-reset', 'Как сбросить ручные правки'),
  // Стол тимлида, KPI
  video('team-desk-stuck', 'Как разобрать зависшие задачи'),
  video('team-desk-queue', 'Как оценить очередь разработчика'),
  video('kpi-review', 'Как разобрать KPI сотрудника и утвердить квартал'),
]);
