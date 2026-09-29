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
};
