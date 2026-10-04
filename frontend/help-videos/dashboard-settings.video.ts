// Ролик «Как настроить дашборд под себя»: шестерёнки виджетов Дашборда —
// «Настройка вида» («Проекты квартала»: колонки и блоки), пороги «Нормированных
// работ», «Пороги активности» («Ворклоги по категориям»), лаг «Баланса часов».
// Результат виден на самих виджетах. Вид и пороги хранятся в браузере (каждый
// ролик снимается в чистом окне), лаг — в профиле: его возвращаем в afterAll.
import { expect, test, type Locator, type Page } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
const YEAR = 2026;
const QUARTER = 3;
const DEMO_LAG = 5;

let originalAppearance: Record<string, unknown> | null = null;

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const ok = (res: { ok(): boolean }) => expect(res.ok()).toBeTruthy();

  ok(await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } }));
  ok(await request.put(`${api}/users/me/period`, { data: { year: YEAR, quarter: QUARTER } }));
  const appearanceRes = await request.get(`${api}/users/me/appearance`);
  ok(appearanceRes);
  originalAppearance = (await appearanceRes.json()) as Record<string, unknown>;
  // Стартуем с лага по умолчанию, чтобы после правки подпись над виджетом менялась заметно.
  ok(await request.put(`${api}/users/me/appearance`, { data: { ...originalAppearance, hours_balance_lag_days: 2 } }));

  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  if (originalAppearance) {
    await request.put(`${api}/users/me/appearance`, { data: originalAppearance });
  }
  await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } });
  await request.put(`${api}/users/me/period`, { data: { year: YEAR, quarter: QUARTER } });
  await request.dispose();
});

/** Очистить числовое поле и набрать значение с видимой скоростью. */
async function retype(d: Director, page: Page, input: Locator, value: string): Promise<void> {
  await d.click(input);
  await page.keyboard.press('Control+A');
  await page.keyboard.type(value, { delay: 120 });
  await d.pause(400);
}

test('dashboard-settings', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  await d.open('/', 'Как настроить дашборд под себя');
  const projectsWidget = page.locator('[data-tour="dash-projects"]');
  await expect(projectsWidget.locator('[data-testid="dash-project-row"]').first()).toBeVisible({ timeout: 20_000 });
  await d.pause(900);
  await d.poster();
  await d.pause(1200);

  // 1. «Проекты квартала»: колонки и блоки.
  const gear = projectsWidget.locator('[data-testid="dash-projects-gear"]');
  await d.click(gear, 'Шестерёнка «Настройка вида» — что показывать в проектах квартала');
  const viewPopover = page.locator('.ant-popover:visible');
  await expect(viewPopover).toBeVisible();
  await d.click(viewPopover.locator('label.ant-checkbox-wrapper', { hasText: 'Тренд' }), 'Уберите ненужные колонки');
  await d.click(viewPopover.locator('label.ant-checkbox-wrapper', { hasText: 'Помощь' }));
  await d.click(viewPopover.locator('label.ant-checkbox-wrapper', { hasText: 'Активность по неделям' }), 'Или целый блок справа');
  await d.waitVoice();
  await d.click(gear);
  await expect(viewPopover).toBeHidden();
  await d.caption('Виджет стал компактнее — этих колонок и блока больше нет');
  await d.show(projectsWidget);
  await d.waitVoice();

  // 2. «Нормированные работы»: пороги.
  const normWidget = page.locator('[data-tour="dash-normed"]');
  await normWidget.scrollIntoViewIfNeeded();
  await d.click(normWidget.locator('.anticon-setting'), 'У нормированных работ — свои пороги загрузки');
  const normModal = page.locator('.ant-modal', { hasText: 'Настройка виджета' });
  await expect(normModal).toBeVisible();
  await retype(d, page, normModal.locator('.ant-input-number input').first(), '95');
  await d.caption('Выше этого процента сотрудник считается перегруженным');
  await d.show(normModal.locator('.ant-input-number').first());
  await d.waitVoice();
  await d.click(normModal.locator('.ant-switch'), 'Можно показать и тех, кто ничего не списал');
  await d.waitVoice();
  await d.click(normModal.getByRole('button', { name: 'Применить' }));
  await expect(normModal).toBeHidden();
  await d.caption('Цвета и список сотрудников пересчитались сразу');
  await d.show(normWidget);
  await d.waitVoice();

  // 3. «Ворклоги по категориям»: пороги активности.
  const catWidget = page.locator('[data-tour="dash-worklogs"]');
  await catWidget.scrollIntoViewIfNeeded();
  await d.click(catWidget.locator('button[aria-label="Пороги активности"]'), 'Пороги активности — сколько дней без списаний допустимо');
  const activityPopover = page.locator('.ant-popover:visible');
  await expect(activityPopover).toBeVisible();
  await retype(d, page, activityPopover.locator('.ant-input-number input').first(), '1');
  await retype(d, page, activityPopover.locator('.ant-input-number input').nth(1), '2');
  await d.waitVoice();
  await d.click(catWidget.locator('button[aria-label="Пороги активности"]'));
  await expect(activityPopover).toBeHidden();
  const worklogCard = catWidget.locator('[data-testid="dash-worklog-card"]').first();
  await worklogCard.scrollIntoViewIfNeeded();
  await d.caption('Карточки сотрудников перекрасились по новым порогам');
  await d.show(worklogCard);
  await d.waitVoice();

  // 4. «Баланс часов»: лаг.
  const balanceWidget = page.locator('[data-tour="dash-balance"]');
  await balanceWidget.scrollIntoViewIfNeeded();
  await d.click(balanceWidget.locator('[data-testid="dash-balance-lag-gear"]'), 'Лаг — на сколько рабочих дней отодвинуть правую границу баланса');
  const lagModal = page.locator('.ant-modal', { hasText: 'Лаг рабочих дней' });
  await expect(lagModal).toBeVisible();
  await retype(d, page, lagModal.locator('.ant-input-number input'), String(DEMO_LAG));
  await d.waitVoice();
  await d.click(lagModal.getByRole('button', { name: 'Сохранить' }));
  await expect(lagModal).toBeHidden();
  await d.caption('Люди списывают часы с задержкой — баланс это учтёт');
  await d.show(balanceWidget);
  await d.waitVoice();
  await d.caption('Лаг хранится в вашем профиле, а вид и пороги — в браузере');
  await d.waitVoice();

  await page.mouse.move(1100, 160);
  await d.caption('Всё это видите только вы — другим настройки не мешают');
  await d.show(page.locator('[data-tour="dash-projects"]'));
  await d.waitVoice();
  await d.caption('Готово', 2200);
  await d.save('dashboard-settings');
});
