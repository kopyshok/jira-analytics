// Общее для глав сводного ролика к релизу.
import { test } from '@playwright/test';
import { mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import type { Director } from '../director.ts';
import { VOICE_ON } from '../voice.ts';
import { CHAPTERS } from './chapters.ts';

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

/** Заголовок главы «3 / 8 · Название»: номер — место главы в оглавлении CHAPTERS. */
export function chapterTitle(title: string): string {
  const n = CHAPTERS.indexOf(title) + 1;
  if (!n) throw new Error(`Главы «${title}» нет в оглавлении chapters.ts`);
  return `${n} / ${CHAPTERS.length} · ${title}`;
}

/**
 * Закрыть окно и сохранить запись главы в data/release-video/clips/<id>.webm, а с диктором
 * (VOICE=1) — и его фразы в <id>.cues.json: голос накладывает склейка.
 */
export async function saveClip(d: Director, id: string): Promise<void> {
  const video = d.page.video();
  if (!video) throw new Error('Запись видео не включена в конфигурации');
  mkdirSync(CLIPS_DIR, { recursive: true });
  const cues = await d.finishVoice();
  await d.page.close();
  await video.saveAs(`${CLIPS_DIR}${id}.webm`);
  // Фразы от прошлой съёмки с диктором к новой записи не подходят.
  if (VOICE_ON) writeFileSync(`${CLIPS_DIR}${id}.cues.json`, JSON.stringify(cues));
  else rmSync(`${CLIPS_DIR}${id}.cues.json`, { force: true });
}
