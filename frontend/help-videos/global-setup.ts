// Вход демо-пользователем до съёмки: ролик начинается сразу с нужной
// страницы, экран входа в кадр не попадает. Сессия (cookie) сохраняется в файл,
// который конфигурация подставляет каждому снимаемому окну.
import { chromium, request, type FullConfig } from '@playwright/test';
import { ADMIN_EMAIL, ADMIN_STATE } from './admin.ts';

const DEMO_EMAIL = 'demo@example.com';
const DEMO_PASSWORD = 'demo12345';

export default async function globalSetup(config: FullConfig) {
  const backendUrl = String(config.metadata.backendUrl);
  const statePath = config.projects[0].use.storageState;
  if (typeof statePath !== 'string') throw new Error('storageState должен быть путём к файлу');

  await login(backendUrl, DEMO_EMAIL, statePath);
  await login(backendUrl, ADMIN_EMAIL, ADMIN_STATE);

  // Прогрев dev-сервера: первая загрузка собирает модули несколько секунд,
  // иначе первый ролик прогона начинается с тёмного экрана.
  const baseURL = config.projects[0].use.baseURL;
  const browser = await chromium.launch();
  const page = await browser.newPage({ storageState: statePath });
  for (const path of ['/', '/capacity', '/planning', '/resource-planning']) {
    // networkidle не наступает: страница держит открытым поток событий сервера.
    await page.goto(`${baseURL}${path}`);
    await page.locator('.topbar').waitFor({ timeout: 90_000 });
  }
  await browser.close();
}

/** Войти пользователем и сохранить сессию в файл; выпуски «Что нового» — прочитанными. */
async function login(backendUrl: string, email: string, path: string): Promise<void> {
  const api = await request.newContext();
  const res = await api.post(`${backendUrl}/api/v1/auth/login`, { data: { email, password: DEMO_PASSWORD } });
  if (!res.ok()) throw new Error(`Вход ${email} не удался: ${res.status()} ${await res.text()}`);
  // Окно «Что нового» закрыло бы кадр.
  const unread = (await (await api.get(`${backendUrl}/api/v1/release-notes/unread`)).json()) as {
    unread_versions: string[];
  };
  for (const version of unread.unread_versions) {
    const seen = await api.post(`${backendUrl}/api/v1/release-notes/mark-seen`, { data: { version } });
    if (!seen.ok()) throw new Error(`Не отмечен выпуск ${version}: ${seen.status()}`);
  }
  await api.storageState({ path });
  await api.dispose();
}
