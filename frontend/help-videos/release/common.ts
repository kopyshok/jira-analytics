// Общее для глав сводного ролика к релизу.
import { type Page, test } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

/** Номер версии в заставке и финале. */
export const RELEASE = '1.12';

/** Глава сводного ролика: 1920×1080 — на экранах планирования справа панель ресурса,
 *  и при 1440 колонки с названиями задач сжимаются до пары слов в строке. */
export const VIEWPORT = { width: 1920, height: 1080 };

/** Куда пишутся главы (папка data/ не попадает в репозиторий). */
export const CLIPS_DIR = fileURLToPath(new URL('../../../data/release-video/clips/', import.meta.url));

/** Подключить в файле главы: кадр 1920×1080 с записью того же размера. */
export function releaseFrame(): void {
  test.use({ viewport: VIEWPORT, video: { mode: 'on', size: VIEWPORT } });
}

/** Адрес API бэкенда съёмки. */
export function apiUrl(): string {
  return `${String(test.info().config.metadata.backendUrl)}/api/v1`;
}

/** Заголовок главы: «3 / 8 · Название». */
export function chapterTitle(n: number, title: string, total = 8): string {
  return `${n} / ${total} · ${title}`;
}

/** Закрыть окно и сохранить запись главы в data/release-video/clips/<id>.webm. */
export async function saveClip(page: Page, id: string): Promise<void> {
  const video = page.video();
  if (!video) throw new Error('Запись видео не включена в конфигурации');
  mkdirSync(CLIPS_DIR, { recursive: true });
  await page.close();
  await video.saveAs(`${CLIPS_DIR}${id}.webm`);
}
