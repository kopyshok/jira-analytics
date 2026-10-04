// Ролик «Как настроить стол тимлида»: Настройки → «Стол тимлида» (демо-администратор):
// группы статусов, очередь работы, «Работа идёт руками», «Не показывать» (добавляем статус),
// «Кто попадает в срез», «Типы задач» → «Сохранить» → раздел «Стол тимлида»: пороги замечаний и
// счётчики статусов в настройках вида. Общие настройки стола возвращаются в afterAll.
import { expect, test, type APIRequestContext } from '@playwright/test';
import { ADMIN_STATE } from './admin.ts';
import { Director } from './director.ts';

test.use({ storageState: ADMIN_STATE });

const TEAM = 'Команда Альфа';
const EXTRA_STATUS = 'Отложено';

const DEFAULT_PREFS = {
  teams: [TEAM], developers: [], mode: 'open', show_reviewed: false, show_done_subtasks: true,
  group_by_developer: true, hidden_columns: ['sprint', 'release', 'daily_rate', 'days'] as string[],
  column_widths: {}, status_counters: [], sprints: [], releases: [],
};

let original: Record<string, unknown> | null = null;

async function adminRequest(playwright: import('@playwright/test').PlaywrightWorkerArgs['playwright']): Promise<APIRequestContext> {
  return playwright.request.newContext({ storageState: ADMIN_STATE });
}

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await adminRequest(playwright);
  const res = await request.get(`${api}/team-desk/settings`);
  expect(res.ok()).toBeTruthy();
  original = (await res.json()) as Record<string, unknown>;
  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  expect((await request.put(`${api}/users/me/team-desk-filter`, { data: DEFAULT_PREFS })).ok()).toBeTruthy();
  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  if (!original) return;
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await adminRequest(playwright);
  const res = await request.put(`${api}/team-desk/settings`, { data: original });
  expect(res.ok(), `${res.status()} ${await res.text()}`).toBeTruthy();
  await request.dispose();
});

test('settings-team-desk', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const card = (title: string) => page.locator('.ant-card', { hasText: title }).filter({ has: page.locator('.ant-card-head-title', { hasText: title }) }).first();
  const toTop = () => page.evaluate(() => window.scrollTo({ top: 0 }));
  const center = (loc: import('@playwright/test').Locator) => loc.evaluate((e) => e.scrollIntoView({ block: 'center' }));

  await d.open('/settings#team-desk', 'Как настроить стол тимлида');
  await expect(card('Группы статусов')).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1100);

  await toTop();
  await d.caption('Здесь решают, какие задачи увидит стол тимлида и как их читать');
  await d.show(page.locator('.ant-alert').first());
  await d.caption('Статусы пишут так же, как они называются в Jira');
  await d.pause(300);
  await d.show(card('Группы статусов'));
  await d.caption('Статусы делят на четыре группы: у разработчика, ждут не его, не начаты, закрыты');
  await d.pause(500);

  await center(card('Очередь работы'));
  await d.caption('«Очередь работы» — статусы, задачи в которых считаются нагрузкой');
  await d.show(card('Очередь работы'));

  await center(card('Работа идёт руками'));
  await d.caption('«Работа идёт руками» — статусы, где разработчик делает задачу сейчас');
  await d.show(card('Работа идёт руками'));

  const hidden = card('Не показывать');
  await center(hidden);
  await d.click(hidden.locator('.ant-select input'), 'Лишний статус можно скрыть совсем');
  await page.keyboard.type(EXTRA_STATUS, { delay: 90 });
  await page.keyboard.press('Enter');
  await page.keyboard.press('Escape');
  await page.mouse.move(60, 120);
  await d.pause(500);

  const roles = card('Кто попадает в срез');
  await center(roles);
  await d.caption('Срез строится по ролям: по умолчанию только разработчики');
  await d.show(roles);
  await d.click(roles.locator('.ant-select'), 'Аналитиков и руководителей проектов в срез не берут');
  await expect(page.locator('.ant-select-dropdown:visible')).toBeVisible();
  await d.pause(600);
  await d.waitVoice();
  await page.keyboard.press('Escape');
  await page.mouse.move(60, 120);

  const types = card('Типы задач');
  await center(types);
  await d.caption('А типы задач подсказывают, что считать декомпозицией');
  await d.show(types);

  const save = page.getByRole('button', { name: 'Сохранить', exact: true });
  await d.click(save, 'Сохраните настройки');
  await expect(page.locator('.ant-message').getByText('Настройки сохранены')).toBeVisible();
  await page.mouse.move(60, 120);
  await d.waitVoice();

  await toTop();
  await d.click(page.locator('.side-item', { hasText: 'Стол тимлида' }), 'Теперь они действуют в разделе «Стол тимлида»');
  const filters = page.locator('[data-tour="desk-filters"]');
  await expect(page.locator('[data-tour="desk-issues"]')).toBeVisible({ timeout: 20_000 });
  await d.click(filters.locator('button[title="Настройки вида"]'), 'Пороги замечаний и счётчики статусов — в настройках вида');
  const panel = page.locator('.ant-card', { hasText: 'ПОРОГИ ПОДСВЕТКИ' }).last();
  await expect(panel).toBeVisible();
  await d.show(panel.getByText('ПОРОГИ ПОДСВЕТКИ'));
  await d.waitVoice();
  await d.show(panel.getByText('СЧЁТЧИКИ СТАТУСОВ'));
  await d.waitVoice();
  await d.click(filters.locator('button[title="Настройки вида"]'));
  await page.mouse.move(700, 120);
  await d.caption('На столе остались только разработчики, а скрытые статусы не видны');
  await d.show(page.getByText('Точность оценок').first(), page.getByText('Точность оценок').nth(1));
  await d.pause(800);

  await d.caption('Готово', 2200);
  await d.save('settings-team-desk');
});
