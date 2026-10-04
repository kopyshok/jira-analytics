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
  video('dashboard-settings', 'Как настроить дашборд под себя'),
  video('projects-portfolio', 'Как посмотреть портфель квартала и план проекта'),
  video('projects-card', 'Как собрать одностраничник проекта'),
  // Категории задач, Аналитика
  video('categorize-issue', 'Как разобрать новые задачи'),
  video('category-to-scenario', 'Как инициатива попадает в сценарий'),
  video('analytics-employee-hours', 'Как посмотреть, куда ушли часы сотрудника'),
  video('analytics-categorize', 'Как разобрать часы без категории прямо из отчёта'),
  video('analytics-groups-flow', 'Как увидеть переток часов между группами'),
  // Ресурсы, рабочий стол аналитика
  video('team-member-add', 'Как добавить сотрудника в команду'),
  video('absence-add', 'Как внести отпуск и увидеть сдвиг плана'),
  video('employee-transfer', 'Как перевести сотрудника в другую группу или команду'),
  video('capacity-team-grid', 'Как читать план и факт команды'),
  video('capacity-roles-desks', 'Как настроить роли и рабочий стол аналитика'),
  video('desk-analyst-use', 'Как пользоваться личным рабочим столом'),
  // Целевые задачи
  video('backlog-idea-add', 'Как завести идею и связать её с Jira'),
  video('backlog-planning-params', 'Как задать параметры планирования'),
  video('backlog-quarter-selection', 'Как отобрать задачи к кварталу'),
  video('backlog-minor-multiteam', 'Как увидеть минорные изменения и кто взял общую задачу'),
  // Сценарии
  video('scenario-create', 'Как собрать сценарий квартала'),
  video('scenario-rules', 'Как задать нормированные работы и вовлечённость'),
  video('scenario-approve', 'Как утвердить сценарий и что дальше'),
  video('scenario-developer', 'Как назначить разработчика в сценарии'),
  video('scenario-review', 'Как пересмотреть сценарий в середине квартала'),
  video('scenario-groups', 'Как вести сценарий команды с группами'),
  video('scenario-multiteam', 'Как увидеть, какие команды уже взяли общую задачу'),
  video('involvement-fact', 'Как сверить план вовлечённости с фактом'),
  // Ресурсное планирование
  video('resource-plan-build', 'Как построить ресурсный план и прочитать его'),
  video('rp-conflicts', 'Как разобрать перегрузки в плане'),
  video('rp-executor', 'Как сменить исполнителя, дату и вовлечённость фазы'),
  video('rp-split', 'Как разбить фазу на двоих'),
  video('rp-blocked-periods', 'Как заблокировать период'),
  video('rp-groups-cross-team', 'Как видеть группы и людей из других команд'),
  video('rp-watch-people', 'Как подобрать людей под план и увидеть, кто свободен'),
  video('rp-other-teams-signals', 'Как понять, что план зависит от других команд'),
  video('rp-reset', 'Как сбросить ручные правки'),
  // Стол тимлида, KPI
  video('team-desk-overview', 'Как быстро оценить состояние команды'),
  video('team-desk-stuck', 'Как разобрать зависшие задачи'),
  video('team-desk-queue', 'Как оценить очередь разработчика'),
  video('team-desk-setup', 'Как настроить стол тимлида под себя'),
  video('kpi-review', 'Как разобрать KPI сотрудника и утвердить квартал'),
  video('kpi-gaps', 'Как понять, почему в ведомости пусто'),
  // Настройки, синхронизация (администратор)
  video('settings-jira-connection', 'Как подключить Jira, проекты и поля'),
  video('sync-schedule-history', 'Как настроить автосинхронизацию'),
  video('settings-work-types', 'Как завести вид нормированных работ'),
  video('settings-team-groups', 'Как разделить команду на группы'),
  video('settings-calendar-reasons', 'Как подготовить календарь и причины отсутствий'),
  video('settings-hierarchy-planning', 'Как отделить служебные эпики от инициатив и настроить планирование'),
  video('settings-users-visibility', 'Как завести пользователя и скрыть лишние разделы'),
  video('settings-kpi', 'Как настроить оценку KPI для роли'),
  video('settings-team-desk', 'Как настроить стол тимлида'),
  video('settings-performance', 'Как понять, почему сервис работает медленно'),
  video('settings-admin-monitoring', 'Как следить за сервисом: использование, обращения, ошибки'),
  // Обратная связь
  video('feedback-send', 'Как сообщить об ошибке или предложить идею'),
]);
