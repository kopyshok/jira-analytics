// Глава «Новое оформление «Пульт»»: дашборд в тёмной Aurora → переключатель тем →
// «Пульт» → меню разделов слева и строка состояния снизу → «Проекты» и «Сценарии»,
// собранные заново → прежние темы на месте. Тема пользователя после главы — «Пульт»:
// следующие главы снимаются в нём.
import { expect, test } from '@playwright/test';
import { Director } from '../director.ts';
import { apiUrl, chapterTitle, releaseFrame, saveClip } from './common.ts';

const TEAM = 'Команда Альфа';

releaseFrame();

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  // Прошлый квартал: в текущем у демо-команды почти нет списаний.
  expect((await request.put(`${api}/users/me/period`, { data: { year: 2026, quarter: 3 } })).ok()).toBeTruthy();
  // Глава начинается в теме по умолчанию — тёмной Aurora.
  expect((await request.put(`${api}/users/me/theme`, { data: { theme: 'aurora-dark' } })).ok()).toBeTruthy();
  await request.dispose();
});

test('01-pult-theme', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  await page.addInitScript(() => localStorage.setItem('app_theme', 'aurora-dark'));
  await d.open('/', chapterTitle('Новое оформление «Пульт»'));

  await expect(page.locator('.topbar')).toBeVisible({ timeout: 60_000 });
  await d.pause(2500);
  await page.mouse.move(900, 500);

  const themeSelect = page.locator('.topbar .ant-select').filter({ hasText: /Aurora/ });
  await d.click(themeSelect, 'В переключателе тем появилось новое оформление — «Пульт»');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: 'Пульт' }));
  await expect(page.locator('html[data-skin="pult"]')).toHaveCount(1);
  await expect(page.locator('.pult-rail')).toBeVisible();
  await page.mouse.move(1100, 500);
  await d.caption('Светлое и строгое: главное — на одном экране');
  await d.pause(3500);

  await d.caption('Слева — узкое меню разделов');
  await d.show(page.locator('.pult-rail'));
  await d.pause(2500);

  await d.caption('Снизу — строка состояния: команда, период, справка и обратная связь');
  await d.show(page.locator('.pult-status'));
  await d.pause(3000);
  await d.waitVoice();

  const railItem = (label: string) => page.locator('.pult-rail-item', { hasText: label });
  await d.click(railItem('Проекты'), 'Разделы собраны заново — например, сводка портфеля проектов');
  await expect(page.locator('.pm').first()).toBeVisible({ timeout: 60_000 });
  await page.mouse.move(1100, 520);
  await d.pause(4000);
  await d.waitVoice();

  await d.click(railItem('Сценарии'), 'Сценарий: ресурс команды и задачи квартала рядом');
  await expect(page.locator('.pm').first()).toBeVisible({ timeout: 60_000 });
  await page.mouse.move(1100, 520);
  await d.pause(4500);

  await d.caption('Прежние темы — Aurora тёмная и светлая — работают как раньше');
  await d.show(page.locator('.pult-status .ant-select').filter({ hasText: /Пульт/ }));
  await d.pause(3500);
  await saveClip(d, '01-pult-theme');

  // Тема, выбранная в кадре, уже сохранена на сервере; на всякий случай — явно.
  const res = await page.context().request.put(`${apiUrl()}/users/me/theme`, { data: { theme: 'pult-light' } });
  expect(res.ok()).toBeTruthy();
});
