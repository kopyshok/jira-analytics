// Глава «Фактическая вовлечённость»: страница сценария демо-команды →
// «Вовлечённость» → «факт» рядом с процентом роли в справочнике (с подсказкой) →
// отчёт «Фактическая вовлечённость»: люди по месяцам, итог квартала,
// «Списано от нормы», среднее по роли. Глава только смотрит — данных не меняет.
import { expect, test } from '@playwright/test';
import { Director } from '../director.ts';
import { chapterTitle, releaseFrame, saveClip } from './common.ts';

/** В демо-базе у команды есть списания аналитика и разработчиков за прошлый квартал. */
const TEAM = 'Команда Альфа';

type Scenario = { id: string; team: string | null; year: number; quarter: string };
type FactCell = { fact: number | null };
type FactResponse = {
  teams: { team: string; roles: { role: string; total: FactCell }[]; people: { name: string; total: FactCell }[] }[];
};

releaseFrame();

let scenarioId = '';

// Данные готовим до открытия окна: иначе в начале ролика — тёмные секунды.
test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const getJson = async <T,>(url: string): Promise<T> => {
    const res = await request.get(url);
    expect(res.ok(), url).toBeTruthy();
    return (await res.json()) as T;
  };

  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();

  // Самый свежий сценарий демо-команды: панель вовлечённости одна для любого.
  const scenarios = await getJson<Scenario[]>(`${api}/planning/scenarios`);
  const scenario = scenarios
    .filter((s) => s.team === TEAM && s.year && s.quarter)
    .sort((a, b) => b.year - a.year || b.quarter.localeCompare(a.quarter))[0];
  expect(scenario, `нет сценария команды ${TEAM}`).toBeTruthy();
  scenarioId = scenario.id;

  // Без списаний за прошлый квартал вместо процентов были бы прочерки — проверяем заранее.
  const fact = await getJson<FactResponse>(
    `${api}/planning/involvement-defaults/fact?teams=${encodeURIComponent(TEAM)}`,
  );
  const roles = fact.teams[0]?.roles ?? [];
  for (const role of ['analyst', 'dev']) {
    expect(typeof roles.find((r) => r.role === role)?.total.fact, `нет факта роли ${role}`).toBe('number');
  }
  await request.dispose();
});

test('06-fact-involvement', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  await d.open(`/planning?scenario=${scenarioId}`, chapterTitle('Фактическая вовлечённость'));

  const openBtn = page.locator('[data-tour="planning-involvement"]');
  await expect(openBtn).toBeVisible({ timeout: 60_000 });
  await expect(page.locator('[data-tour="planning-capacity-panel"]')).toBeVisible({ timeout: 60_000 });
  await d.pause(1200);

  await d.click(openBtn, 'На странице сценария откройте «Вовлечённость»');
  const drawer = page.locator('.ant-drawer-open .ant-drawer-section');
  await expect(drawer).toBeVisible();
  // Первая таблица панели — «По ролям команды».
  const roles = drawer.locator('.ant-table').first();
  const facts = roles.getByTestId('involvement-fact');
  await expect(facts.first()).toBeVisible();
  await expect(facts.first()).toContainText(/факт \d+%/);
  // Панель выезжает справа: рамку ставим, когда она встала на место.
  await d.pause(500);
  await page.mouse.move(700, 120);

  await d.caption('Рядом с процентом роли теперь виден факт прошлого квартала');
  await d.show(roles);
  await d.pause(2000);
  // Подсказка у «факта»: квартал, сколько людей, дней с проектами и списано от нормы.
  const devFact = roles.locator('.ant-table-row', { hasText: 'Разработка' }).getByTestId('involvement-fact');
  // Рамка с курсором сбоку: точка курсора не закрывает цифру.
  await d.show(devFact);
  await devFact.hover();
  await expect(page.locator('.ant-tooltip:visible')).toContainText('списано от нормы');
  await d.pause(3500);
  await page.mouse.move(700, 120);

  await d.click(
    drawer.getByTestId('involvement-fact-report'),
    'Подробности — в отчёте «Фактическая вовлечённость»',
  );
  const report = page.locator('.ant-modal:visible', { hasText: 'Фактическая вовлечённость' });
  await expect(report).toBeVisible();
  const table = report.locator('.ant-table');
  await expect(table.locator('.ant-table-row').first()).toBeVisible({ timeout: 30_000 });
  await expect(table).toContainText('Итог квартала');
  // Окно появляется с увеличением: рамку ставим, когда оно встало на место.
  await d.pause(600);

  await d.caption('Считаются только дни, когда человек работал над проектами');
  await d.show(report.locator('.ant-typography').first());
  await d.pause(3200);

  const first = table.locator('.ant-table-row').first();
  await d.caption('По каждому человеку — факт по месяцам и итог квартала');
  await d.show(first);
  await d.pause(1500);
  // Подсказка у итога квартала: из каких часов сложился процент.
  const cells = first.locator('td');
  const total = cells.nth((await cells.count()) - 2).locator('.ant-typography');
  await d.show(total);
  await total.hover();
  await expect(page.locator('.ant-tooltip:visible')).toContainText('Дней с проектами');
  await d.pause(3200);
  await page.mouse.move(700, 120);

  const average = table.locator('.ant-table-row', { hasText: 'Среднее по роли' });
  await d.caption('Ниже — среднее по роли и сколько списано от нормы');
  await d.show(average.last());
  await d.pause(3500);
  await saveClip(d, '06-fact-involvement');
});
