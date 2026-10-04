// Ролик «Как сверить план вовлечённости с фактом»: утверждённый сценарий команды →
// «Вовлечённость» → справочник по ролям, рядом с планом — «факт» → отчёт
// «Фактическая вовлечённость» (команды и квартал, месяцы, «Итог квартала»,
// «Списано от нормы», «Среднее по роли») → обратно в справочник: правка процента.
// Данные не подсаживаются: у демо-команды есть списания по проектным задачам за прошлый
// квартал. Справочник и сценарии ролик не меняет (правка процента отменяется).
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';

interface ScenarioItem {
  id: string;
  year: number | null;
  quarter: string | null;
  team: string | null;
}

let scenarioId = '';

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();

  // Панель вовлечённости работает от команды сценария — берём последний утверждённый.
  const res = await request.get(`${api}/planning/scenarios`, { params: { status: 'approved', teams: TEAM } });
  expect(res.ok()).toBeTruthy();
  const approved = ((await res.json()) as ScenarioItem[]).filter(
    (s) => s.team === TEAM && s.year != null && s.quarter != null,
  );
  expect(approved.length, `нет утверждённых сценариев команды ${TEAM}`).toBeGreaterThan(0);
  scenarioId = approved.sort((a, b) => `${a.year} ${a.quarter}`.localeCompare(`${b.year} ${b.quarter}`)).at(-1)!.id;
  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } });
  await request.dispose();
});

test('involvement-fact', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  await d.open(`/planning?scenario=${scenarioId}`, 'Как сверить план вовлечённости с фактом');
  await expect(page.locator('[data-tour="planning-involvement"]')).toBeVisible({ timeout: 15_000 });
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  // === Справочник по ролям и «факт» рядом с планом ===
  await d.click(page.locator('[data-tour="planning-involvement"]'), 'Откройте панель «Вовлечённость»');
  const drawer = page.locator('.ant-drawer-open');
  await expect(drawer).toBeVisible();
  const factLabel = drawer.locator('[data-testid="involvement-fact"]').first();
  await expect(factLabel).toBeVisible({ timeout: 15_000 });
  await d.pause(400);

  await d.caption('В справочнике — плановая вовлечённость по ролям');
  await d.show(drawer.getByRole('heading', { name: 'По ролям команды' }));
  await d.pause(600);

  await d.caption('Рядом с планом — факт за прошлый квартал');
  await d.show(factLabel);
  await d.pause(600);

  await d.caption('Факт считается по дням с проектными списаниями');
  await factLabel.hover();
  await expect(page.locator('.ant-tooltip:visible')).toBeVisible();
  await d.pause(1200);
  await page.mouse.move(700, 40);

  // === Отчёт «Фактическая вовлечённость» ===
  await d.click(drawer.locator('[data-testid="involvement-fact-report"]'), 'Откройте «Фактическая вовлечённость»');
  const modal = page.locator('.ant-modal', { hasText: 'Фактическая вовлечённость' });
  await expect(modal).toBeVisible();
  const avgRow = modal.locator('tr', { hasText: 'Среднее по роли' }).first();
  await expect(avgRow).toBeVisible({ timeout: 20_000 });
  await d.pause(400);

  await d.caption('Здесь выбираются команды и квартал');
  await d.show(modal.locator('.ant-select').first(), modal.locator('.ant-select').nth(1));
  await d.pause(500);

  const quarterSelect = modal.locator('.ant-select').nth(1);
  await d.click(quarterSelect);
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option').nth(2));
  await expect(avgRow).toBeVisible({ timeout: 20_000 });
  await d.pause(500);
  await d.click(quarterSelect);
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option').nth(1));
  await expect(avgRow).toBeVisible({ timeout: 20_000 });
  await page.mouse.move(700, 40);
  await d.pause(500);

  const heads = modal.locator('thead th');
  await d.caption('Факт — по каждому месяцу квартала');
  await d.show(heads.nth(2), heads.nth(4));
  await d.pause(500);

  await d.caption('«Итог квартала» — факт за весь квартал');
  await d.show(modal.locator('thead th', { hasText: 'Итог квартала' }));
  await d.pause(500);

  await d.caption('«Списано от нормы» — доля часов от нормы квартала');
  await d.show(modal.locator('thead th', { hasText: 'Списано от нормы' }));
  await d.pause(500);

  await d.caption('«Среднее по роли» сверяется со справочником');
  await d.show(avgRow);
  await d.pause(600);

  await d.caption('В подсказке ячейки — дни с проектной работой');
  const cell = modal.locator('tbody tr.ant-table-row').first().locator('td').nth(2).locator('.ant-typography');
  await d.point(cell);
  await cell.hover();
  await expect(page.locator('.ant-tooltip:visible')).toBeVisible();
  await d.pause(1400);
  await page.mouse.move(700, 40);

  // === Назад в справочник: поправить процент ===
  await d.waitVoice();
  await d.click(modal.locator('.ant-modal-close'), 'Закройте отчёт');
  await expect(modal).toBeHidden();

  await d.caption('Если план далёк от факта — поправьте процент роли');
  await d.click(drawer.getByRole('button', { name: 'Изменить запись' }).first());
  await expect(drawer.getByRole('button', { name: 'Отмена' })).toBeVisible();
  const pct = drawer.locator('.ant-input-number-input').nth(1);
  await pct.click();
  await pct.press('Control+A');
  await pct.pressSequentially('70', { delay: 90 });
  await d.show(pct);
  await d.pause(800);
  await d.waitVoice();
  await d.click(drawer.getByRole('button', { name: 'Отмена' }));
  await page.mouse.move(700, 40);

  await d.caption('Готово', 2200);
  await d.save('involvement-fact');
});
