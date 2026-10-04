// Ролик «Как быстро оценить состояние команды»: Стол тимлида → «Светофор»
// (плитки разработчиков, точность оценок, шкала часов) → клик по плитке
// оставляет одного человека, повторный клик снимает → «Проблемы вперёд»
// (шкала недобора и перебора) → полоса «Задачи по статусам» → «Сбросить».
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';

const DEFAULT_PREFS = {
  teams: [TEAM], developers: [], mode: 'open', show_reviewed: false, show_done_subtasks: true,
  group_by_developer: true, hidden_columns: ['sprint', 'release', 'daily_rate', 'days'] as string[], column_widths: {}, status_counters: [],
  sprints: [], releases: [],
};

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  expect((await request.put(`${api}/users/me/team-desk-filter`, { data: DEFAULT_PREFS })).ok()).toBeTruthy();
  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  await request.put(`${api}/users/me/team-desk-filter`, { data: DEFAULT_PREFS }).catch(() => undefined);
  await request.dispose();
});

test('team-desk-overview', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  await d.open('/team-desk', 'Как быстро оценить состояние команды');

  const tiles = page.locator('.ant-card-hoverable');
  await expect(tiles.first()).toBeVisible({ timeout: 20_000 });
  await d.pause(1100);
  await d.poster();
  await d.pause(1500);

  const tabs = page.locator('[data-tour="desk-tabs"]');
  await d.caption('Раскладка «Светофор» — плитка на каждого разработчика');
  await d.show(tabs);
  await d.pause(500);

  const first = tiles.first();
  await d.caption('Левый край плитки красный или жёлтый, если есть замечания');
  await d.show(first);
  await d.pause(600);

  await d.caption('Точность оценок и шкала часов — сколько списано против оценки');
  await d.show(first.getByText('точность оценок'));
  await d.pause(600);

  const flags = page.locator('[data-tour="desk-flags"]');
  await d.click(first.locator('strong').first(), 'Нажмите на плитку — в списке останется один разработчик');
  await expect(flags.getByText('ОТОБРАНО')).toBeVisible();
  await d.caption('Сверху видно, что отобран один человек');
  await d.show(flags.locator('.ant-tag-blue').first());
  await d.pause(600);

  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
  await d.click(first.locator('strong').first(), 'Ещё один клик по плитке снимает выбор');
  await expect(flags.getByText('ОТОБРАНО')).toHaveCount(0);
  await page.mouse.move(1100, 180);
  await d.pause(500);

  await d.click(tabs.locator('.ant-tabs-tab', { hasText: 'Проблемы вперёд' }), 'Откройте раскладку «Проблемы вперёд»');
  const issues = page.locator('[data-tour="desk-issues"]');
  await expect(issues).toBeVisible();
  await d.caption('Здесь задачи сгруппированы по людям');
  await d.show(issues);
  await d.pause(500);

  const scaleHead = issues.locator('th', { hasText: 'Недобор' });
  await d.caption('Шкала показывает недобор влево и перебор вправо от оценки');
  await d.show(scaleHead);
  await d.pause(600);

  const statusBar = flags.locator('.ant-card', { hasText: 'ЗАДАЧИ ПО СТАТУСАМ' });
  await statusBar.scrollIntoViewIfNeeded();
  await d.caption('Полоса «Задачи по статусам» — все статусы среза с числом задач');
  await d.show(statusBar);
  await d.pause(500);

  await d.click(statusBar.locator('.ant-tag').first(), 'Нажмите на статус — останутся задачи только в нём');
  await expect(flags.getByText('ОТОБРАНО')).toBeVisible();
  await page.mouse.move(1100, 180);
  await d.caption('В «Отобрано» видно, что список урезан');
  await d.show(flags.locator('.ant-tag-blue').first());
  await d.pause(600);

  await d.click(flags.getByRole('button', { name: 'Сбросить', exact: true }), 'Кнопка «Сбросить» возвращает всю команду');
  await expect(flags.getByText('ОТОБРАНО')).toHaveCount(0);
  await page.mouse.move(1100, 180);
  await d.pause(500);

  await d.show(issues);
  await d.caption('Готово', 2200);
  await d.pause(500);
  await d.save('team-desk-overview');
});
