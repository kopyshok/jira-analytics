// Ролик «Как настроить стол тимлида под себя»: Стол тимлида → «Отдельные люди»
// → «Релиз» → режим «За период» → «выполненные подзадачи» → шестерёнка
// (галочки «Отслеживать», пороги, «Счётчики статусов») → «по людям / списком»
// → «Колонки» → сортировка по заголовку.
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';

const DEFAULT_PREFS = {
  teams: [TEAM], developers: [], mode: 'open', show_reviewed: false, show_done_subtasks: true,
  group_by_developer: true, hidden_columns: ['sprint', 'release', 'daily_rate', 'days'] as string[],
  column_widths: {}, status_counters: [], sprints: [], releases: [],
};

async function resetPrefs(playwright: import('@playwright/test').PlaywrightWorkerArgs['playwright'], testInfo: import('@playwright/test').TestInfo) {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  expect((await request.put(`${api}/users/me/team-desk-filter`, { data: DEFAULT_PREFS })).ok()).toBeTruthy();
  await request.dispose();
}

test.beforeAll(async ({ playwright }, testInfo) => {
  await resetPrefs(playwright, testInfo);
});

// Всё, что ролик менял, — личные настройки вида; общие пороги не сохраняются.
test.afterAll(async ({ playwright }, testInfo) => {
  await resetPrefs(playwright, testInfo).catch(() => undefined);
});

test('team-desk-setup', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  await d.open('/team-desk', 'Как настроить стол тимлида под себя');

  const filters = page.locator('[data-tour="desk-filters"]');
  const issues = page.locator('[data-tour="desk-issues"]');
  await expect(issues).toBeVisible({ timeout: 20_000 });
  await d.pause(1100);
  await d.poster();
  await d.pause(1500);

  const option = () => page.locator('.ant-select-dropdown:visible .ant-select-item-option').first();

  // Порядок полей шапки: команды, отдельные люди, спринт, релиз.
  await d.click(filters.locator('.ant-select').nth(1), 'В поле «Отдельные люди» можно добрать разработчика');
  await d.click(option());
  await page.keyboard.press('Escape');
  await page.mouse.move(700, 120);
  await d.pause(700);

  const releaseSelect = filters.locator('.ant-select').nth(3);
  await d.click(releaseSelect, 'Список сужается и одним релизом');
  await d.click(option());
  await page.keyboard.press('Escape');
  await page.mouse.move(700, 120);
  await d.pause(900);
  // Релиз снимаем тихо: вместе с остальными отборами список мог бы опустеть.
  await d.pause(500);
  await releaseSelect.locator('input').press('Backspace');
  await expect(releaseSelect.locator('.ant-select-selection-item')).toHaveCount(0);
  await page.mouse.move(700, 120);

  await d.click(filters.getByText('За период', { exact: true }), 'Режим «За период» берёт задачи за выбранные даты');
  await expect(filters.locator('.ant-picker-range')).toBeVisible();
  await d.show(filters.locator('.ant-picker-range'));
  await d.pause(500);
  await d.click(filters.getByText('Открытые сейчас', { exact: true }), 'А «Открытые сейчас» — только то, что в работе');
  await page.mouse.move(700, 120);

  await d.click(filters.locator('.ant-switch').nth(1), 'Тумблер «выполненные подзадачи» скрывает закрытые подзадачи');
  await d.pause(700);
  await d.click(filters.locator('.ant-switch').nth(1));
  await d.pause(300);

  await d.click(filters.locator('button[title="Настройки вида"]'), 'Шестерёнка открывает настройки вида');
  const panel = page.locator('.ant-card', { hasText: 'ПОРОГИ ПОДСВЕТКИ' }).last();
  await expect(panel).toBeVisible();
  await d.show(panel);
  await d.pause(500);

  await d.caption('Галочки «Отслеживать» решают, какие замечания считать');
  await d.show(panel.getByText('ОТСЛЕЖИВАТЬ'));
  await d.pause(500);
  await d.caption('Пороги подсветки общие для всей команды, их сохраняют кнопкой');
  await d.show(panel.getByRole('button', { name: 'Сохранить' }));
  await d.pause(500);
  await d.caption('«Счётчики статусов» выбирают, какие статусы показывать на плитках');
  await d.show(panel.getByText('СЧЁТЧИКИ СТАТУСОВ'));
  await d.pause(500);
  await d.waitVoice();
  await d.click(filters.locator('button[title="Настройки вида"]'), 'Закройте настройки');
  await page.mouse.move(700, 120);

  await issues.scrollIntoViewIfNeeded();
  await d.click(issues.locator('.ant-switch').first(), 'Переключатель «по людям» и «списком» меняет вид задач');
  await d.pause(700);

  const columnsBtn = issues.getByRole('button', { name: 'Колонки' });
  await d.click(columnsBtn, '«Колонки» показывают и прячут столбцы');
  await d.click(page.locator('.ant-dropdown-menu-item', { hasText: 'Шкала' }));
  await page.keyboard.press('Escape');
  await page.mouse.move(700, 120);
  await d.pause(700);

  await d.click(issues.locator('th', { hasText: 'Оценка' }), 'Клик по заголовку сортирует задачи');
  await page.mouse.move(700, 120);
  await d.pause(700);

  await d.caption('Вид запоминается за вами, а пороги общие для команды');
  await d.show(issues);
  await d.pause(500);
  await d.caption('Готово', 2200);
  await d.pause(500);
  await d.save('team-desk-setup');
});
