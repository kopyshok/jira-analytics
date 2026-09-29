// Ролик «Как отобрать задачи к кварталу»: вкладки «Активные» / «Бэклог» / «Архив»,
// группировка по кварталам, метки «Только спорные» и «Не в плане», приоритет →
// выключили «В план» — кандидат пропал из черновика сценария → архивирование
// и возврат из архива.
import { expect, test, type APIRequestContext } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
const SCENARIO_NAME = 'Проверка отбора кандидатов';
const IDEA_TITLE = 'Настройка отчёта по остаткам';

interface ScenarioListItem { id: string; team: string | null; year: number | null; quarter: string | null }

/** Первый квартал, для которого у команды ещё нет сценария (не раньше текущего) —
 *  ролик детерминирован в любой день и не портит существующие сценарии команды. */
async function nextFreeQuarter(request: APIRequestContext, api: string): Promise<{ year: number; quarter: number }> {
  const res = await request.get(`${api}/planning/scenarios`, { params: { teams: TEAM } });
  expect(res.ok()).toBeTruthy();
  const list: ScenarioListItem[] = await res.json();
  const keys = list
    .filter((s) => s.team === TEAM && s.year != null && s.quarter != null)
    .map((s) => (s.year as number) * 4 + (Number((s.quarter as string).replace('Q', '')) - 1));
  const now = new Date();
  const currentKey = now.getFullYear() * 4 + Math.floor(now.getMonth() / 3);
  const nextKey = Math.max(currentKey, ...keys) + 1;
  return { year: Math.floor(nextKey / 4), quarter: (nextKey % 4) + 1 };
}

interface Ctx {
  scenarioId: string;
  itemId: string;
  itemTitle: string;
}

let ctx: Ctx | null = null;

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();

  // Свежая ручная идея, а не случайная задача из бэклога: у существующих задач
  // почти наверняка есть раскладка (пусть и не отмеченная галочкой) в одном из
  // утверждённых сценариев команды — архивировать такую сервис не даст.
  const createdIdea = await request.post(`${api}/backlog`, {
    data: {
      title: IDEA_TITLE, team: TEAM,
      estimate_analyst_hours: 8, estimate_dev_hours: 16, estimate_qa_hours: 4,
    },
  });
  expect(createdIdea.ok()).toBeTruthy();
  const idea: { id: string; title: string } = await createdIdea.json();

  const { year, quarter } = await nextFreeQuarter(request, api);
  const created = await request.post(`${api}/planning/scenarios`, {
    data: { name: SCENARIO_NAME, year, quarter, team: TEAM },
  });
  expect(created.ok()).toBeTruthy();
  const scenario: { id: string } = await created.json();

  ctx = {
    scenarioId: scenario.id,
    itemId: idea.id,
    itemTitle: idea.title,
  };
  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  if (!ctx) return;
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  await request.delete(`${api}/planning/scenarios/${ctx.scenarioId}`);
  await request.delete(`${api}/backlog/${ctx.itemId}`);
  await request.dispose();
});

test('backlog-quarter-selection', async ({ page }) => {
  if (!ctx) throw new Error('Данные не подготовлены (beforeAll)');
  const c = ctx;
  const d = new Director(page);
  await d.install();

  await d.open('/backlog', 'Как отобрать задачи к кварталу');
  const pane = page.locator('[data-tour="backlog-tabs"] .ant-tabs-tabpane-active');
  await expect(pane.locator('tbody tr.ant-table-row').first()).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  const tabs = page.locator('[data-tour="backlog-tabs"] .ant-tabs-nav');
  await d.caption('Три вкладки: задачи квартала, бэклог кандидатов и архив');
  await d.show(tabs);
  await d.pause(1400);

  const groupBtn = page.getByRole('button', { name: /Группировать по кварталам|Сгруппировано по кварталам/ });
  await d.click(groupBtn, 'Активные задачи можно сгруппировать по кварталам');
  await d.pause(1200);
  await d.click(groupBtn);

  await d.click(
    page.locator('[data-tour="backlog-tabs"] .ant-tabs-tab', { hasText: 'Бэклог' }),
    'На вкладке «Бэклог» — кандидаты в квартал',
  );

  const row = pane.locator(`tr[data-row-key="${c.itemId}"]`);
  await expect(row).toBeVisible({ timeout: 15_000 });
  await row.scrollIntoViewIfNeeded();

  const disputedTag = page.locator('.ant-tag', { hasText: 'Только спорные' });
  if (await disputedTag.count()) {
    await d.click(disputedTag, 'Метка «Только спорные» оставляет задачи с расхождением оценок в Jira');
    await d.pause(1400);
    await d.click(disputedTag);
  }

  const prioInput = row.locator('td').first().locator('input');
  await d.click(prioInput, 'Расставьте приоритет — чем меньше число, тем выше идея');
  await prioInput.press('Control+A');
  await prioInput.pressSequentially('2', { delay: 90 });
  await prioInput.press('Tab');
  await d.pause(600);

  const inPlanSwitch = row.getByRole('switch');
  await d.click(inPlanSwitch, 'Заведомо непроходную идею выключите из плана');
  await expect(inPlanSwitch).not.toBeChecked();
  await page.mouse.move(1100, 160);

  const offPlanTag = page.locator('.ant-tag', { hasText: 'Не в плане' });
  await expect(offPlanTag).toBeVisible({ timeout: 15_000 });
  await d.click(offPlanTag, 'Метка «Не в плане» собирает все выключенные идеи');
  await expect(row).toBeVisible();
  await d.pause(1400);
  await d.click(offPlanTag);

  await d.click(page.locator('.side-item', { hasText: 'Сценарии' }), 'Перейдите в «Сценарии»');
  const select = page.locator('[data-tour="planning-scenario-select"]');
  await expect(select).toBeVisible();
  await d.click(select);
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: SCENARIO_NAME }));

  const candidateRow = page.locator('[data-flip-wrapper]', { hasText: c.itemTitle });
  await expect(page.locator('[data-flip-wrapper]').first()).toBeVisible({ timeout: 15_000 });
  await expect(candidateRow).toHaveCount(0);
  await d.caption('Выключенной задачи в черновике сценария больше нет');
  await d.show(page.locator('[data-tour="planning-capacity-panel"]'));
  await d.pause(2000);

  await d.click(page.locator('.side-item', { hasText: 'Целевые задачи' }), 'Вернитесь в «Целевые задачи»');
  await d.click(page.locator('[data-tour="backlog-tabs"] .ant-tabs-tab', { hasText: 'Бэклог' }));
  const row2 = pane.locator(`tr[data-row-key="${c.itemId}"]`);
  await expect(row2).toBeVisible({ timeout: 15_000 });

  await d.click(row2.locator('[data-tour="backlog-archive"]'), 'Инициативу можно отправить в архив');
  const archivePopconfirm = page.locator('.ant-popconfirm:visible');
  await expect(archivePopconfirm).toBeVisible();
  await d.click(archivePopconfirm.getByRole('button', { name: 'OK' }), 'Подтвердите');
  await expect(row2).toHaveCount(0);

  await d.click(
    page.locator('[data-tour="backlog-tabs"] .ant-tabs-tab', { hasText: 'Архив' }),
    'Задача переехала в «Архив»',
  );
  const archivedRow = pane.locator(`tr[data-row-key="${c.itemId}"]`);
  await expect(archivedRow).toBeVisible({ timeout: 15_000 });
  await archivedRow.scrollIntoViewIfNeeded();

  await d.click(archivedRow.locator('[data-tour="backlog-restore"]'), 'И вернуть обратно в бэклог');
  const restorePopconfirm = page.locator('.ant-popconfirm:visible');
  await expect(restorePopconfirm).toBeVisible();
  await d.click(restorePopconfirm.getByRole('button', { name: 'OK' }), 'Подтвердите');
  await expect(archivedRow).toHaveCount(0);

  await d.click(
    page.locator('[data-tour="backlog-tabs"] .ant-tabs-tab', { hasText: 'Бэклог' }),
    'Снова на «Бэклог» — идея на месте',
  );
  const backRow = pane.locator(`tr[data-row-key="${c.itemId}"]`);
  await expect(backRow).toBeVisible({ timeout: 15_000 });
  await backRow.scrollIntoViewIfNeeded();
  await d.show(backRow);
  await d.pause(1600);

  await d.caption('Готово', 2200);
  await d.save('backlog-quarter-selection');
});
