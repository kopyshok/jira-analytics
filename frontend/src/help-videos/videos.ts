export interface VideoInfo {
  title: string;
  src: string;
  poster: string;
}

const BASE = `${import.meta.env.BASE_URL}help-videos/`;

/** Реестр роликов-инструкций: id → название, файл, обложка. */
export const VIDEOS: Record<string, VideoInfo> = {
  'absence-add': {
    title: 'Как внести отпуск',
    src: `${BASE}absence-add.webm`,
    poster: `${BASE}absence-add.jpg`,
  },
  'categorize-issue': {
    title: 'Как отнести задачу к категории',
    src: `${BASE}categorize-issue.webm`,
    poster: `${BASE}categorize-issue.jpg`,
  },
  'team-member-add': {
    title: 'Как добавить сотрудника в команду',
    src: `${BASE}team-member-add.webm`,
    poster: `${BASE}team-member-add.jpg`,
  },
  'backlog-idea-add': {
    title: 'Как завести идею и оценить её по ролям',
    src: `${BASE}backlog-idea-add.webm`,
    poster: `${BASE}backlog-idea-add.jpg`,
  },
  'backlog-planning-params': {
    title: 'Как задать параметры планирования',
    src: `${BASE}backlog-planning-params.webm`,
    poster: `${BASE}backlog-planning-params.jpg`,
  },
  'scenario-create': {
    title: 'Как собрать сценарий квартала',
    src: `${BASE}scenario-create.webm`,
    poster: `${BASE}scenario-create.jpg`,
  },
  'scenario-rules': {
    title: 'Как поправить нормированные работы',
    src: `${BASE}scenario-rules.webm`,
    poster: `${BASE}scenario-rules.jpg`,
  },
  'scenario-approve': {
    title: 'Как утвердить сценарий',
    src: `${BASE}scenario-approve.webm`,
    poster: `${BASE}scenario-approve.jpg`,
  },
  'resource-plan-build': {
    title: 'Как построить ресурсный план',
    src: `${BASE}resource-plan-build.webm`,
    poster: `${BASE}resource-plan-build.jpg`,
  },
  'resource-plan-phase': {
    title: 'Как перенести фазу вручную',
    src: `${BASE}resource-plan-phase.webm`,
    poster: `${BASE}resource-plan-phase.jpg`,
  },
  'analytics-employee-hours': {
    title: 'Как посмотреть, куда ушли часы сотрудника',
    src: `${BASE}analytics-employee-hours.webm`,
    poster: `${BASE}analytics-employee-hours.jpg`,
  },
  'team-desk-stuck': {
    title: 'Как разобрать зависшие задачи',
    src: `${BASE}team-desk-stuck.webm`,
    poster: `${BASE}team-desk-stuck.jpg`,
  },
};
