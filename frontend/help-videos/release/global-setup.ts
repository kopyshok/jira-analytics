// Подготовка сводного ролика: вход демо-пользователем (как у роликов справки) и окно
// «Что нового» текущей версии отмечено просмотренным — иначе после выпуска оно
// всплывает поверх первой главы и закрывает кадр.
import { request, type FullConfig } from '@playwright/test';
import { readFileSync } from 'node:fs';
import baseSetup from '../global-setup.ts';

export default async function globalSetup(config: FullConfig) {
  await baseSetup(config);
  const { version } = JSON.parse(readFileSync(new URL('../../package.json', import.meta.url), 'utf-8')) as {
    version: string;
  };
  const api = await request.newContext({ storageState: config.projects[0].use.storageState as string });
  const res = await api.post(`${String(config.metadata.backendUrl)}/api/v1/release-notes/mark-seen`, {
    data: { version: `v${version}` },
  });
  await api.dispose();
  if (!res.ok()) throw new Error(`Не удалось отметить «Что нового» просмотренным: ${res.status()}`);
}
