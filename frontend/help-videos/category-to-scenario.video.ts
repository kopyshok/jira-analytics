// Ролик «Как инициатива попадает в сценарий»: Категории задач → задаче выбрать
// категорию «Инициативы и RFA» и сохранить → «Целевые задачи» → вкладка «Бэклог»:
// строка появилась сама → «Сценарии»: задача среди кандидатов черновика.
// Черновик сценария команды на свободный квартал создаётся в beforeAll (API) и
// удаляется в afterAll — он существует только на время этого ролика.
import { expect, test, type Locator, type Page } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
const CATEGORY = 'Инициативы и RFA';
const CATEGORY_CODE = 'initiatives_rfa';

/**
 * Открыть выпадающий список (категории, сценарии — любой AntD Select) и выбрать
 * опцию по тексту. Список рендерится виртуально и открывается со скроллом к уже
 * стоящему значению — нужная опция может быть не отрисована вовсе, пока не прокрутить.
 */
async function pickOption(d: Director, page: Page, trigger: Locator, label: string, caption?: string): Promise<void> {
  await d.click(trigger, caption);
  const dropdown = page.locator('.ant-select-dropdown:visible');
  await expect(dropdown).toBeVisible();
  const option = dropdown.locator('.ant-select-item-option', { hasText: label });
  await dropdown.hover();
  for (let i = 0; i < 20 && (await option.count()) === 0; i++) {
    await page.mouse.wheel(0, 120);
    await page.waitForTimeout(80);
  }
  await expect(option.first()).toBeVisible({ timeout: 5_000 });
  await d.click(option.first());
}

interface ScenarioListItem {
  year: number | null;
  quarter: string | null;
  team: string | null;
}
interface IssueRoot {
  id: string;
  key: string;
  summary: string;
  category: string | null;
  assigned_category: string | null;
  category_verified: boolean;
  is_context: boolean;
  has_children: boolean;
  descendant_match_count: number;
}
interface BacklogListItem {
  id: string;
  jira_key: string | null;
  included_in_planning: boolean;
}
interface Alloc {
  id: string;
  backlog_item_id: string;
}

let scenarioId = '';
let scenarioName = '';
let candidate: IssueRoot | undefined;

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

  // Первый свободный квартал команды — сценарий детерминирован в любой день.
  const scenarios = await getJson<ScenarioListItem[]>(`${api}/planning/scenarios?teams=${encodeURIComponent(TEAM)}`);
  const keys = scenarios
    .filter((s) => s.team === TEAM && s.year != null && s.quarter != null)
    .map((s) => (s.year as number) * 4 + (Number((s.quarter as string).replace('Q', '')) - 1));
  const now = new Date();
  const currentKey = now.getFullYear() * 4 + Math.floor(now.getMonth() / 3);
  const nextKey = Math.max(currentKey, ...keys) + 1;
  const year = Math.floor(nextKey / 4);
  const quarter = (nextKey % 4) + 1;
  scenarioName = `${year} Q${quarter} ${TEAM}`;

  const created = await request.post(`${api}/planning/scenarios`, {
    data: { name: scenarioName, year, quarter, team: TEAM },
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  scenarioId = (await created.json()).id as string;

  // Задача-контейнер (эпик/инициатива) без категории «Инициативы и RFA» — на ней
  // покажем, как категория сама протягивает задачу в бэклог и в сценарий.
  // Предпочитаем «чистую» (без своих неподтверждённых потомков) — тогда строка
  // после сохранения сразу и видимо уходит из «К разбору».
  const roots = await getJson<IssueRoot[]>(
    `${api}/issues/tree/roots?teams=${encodeURIComponent(TEAM)}&tab=stack`,
  );
  const eligible = roots.filter((r) => r.is_container && !r.is_context && r.category !== CATEGORY_CODE);
  candidate = eligible.find((r) => r.descendant_match_count === 0) ?? eligible[0];
  expect(candidate, `В «К разбору» команды ${TEAM} нет подходящей задачи-контейнера`).toBeTruthy();

  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  if (scenarioId) await request.delete(`${api}/planning/scenarios/${scenarioId}`);
  await request.dispose();
});

/** Дождаться, пока задача попадёт в бэклог как BacklogItem, и включить её в план,
 *  если синхронизация категории создала элемент с выключенной галочкой «В план». */
async function ensureIncludedInPlanning(page: Page, api: string, key: string): Promise<void> {
  for (let i = 0; i < 10; i++) {
    const res = await page.request.get(`${api}/backlog`, { params: { view: 'active', teams: TEAM } });
    expect(res.ok()).toBeTruthy();
    const items = (await res.json()) as BacklogListItem[];
    const item = items.find((it) => it.jira_key === key);
    if (item) {
      if (!item.included_in_planning) {
        await page.request.patch(`${api}/backlog/${item.id}/included`, { data: { included: true } });
      }
      return;
    }
    await page.waitForTimeout(500);
  }
  throw new Error(`Задача ${key} не появилась в бэклоге`);
}

test('category-to-scenario', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const api = `${String(test.info().config.metadata.backendUrl)}/api/v1`;
  const issue = candidate!;

  await d.open('/categories', 'Как инициатива попадает в сценарий');
  const table = page.locator('[data-tour="categories-table"]');
  const row = table.locator(`tr[data-row-key="${issue.id}"]`);
  await expect(row).toBeVisible({ timeout: 20_000 });
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  await d.caption('В «К разбору» лежит эпик, который на самом деле — инициатива');
  await d.show(row);
  await d.pause(1800);

  await pickOption(d, page, row.locator('.ant-select'), CATEGORY, 'Выберите задаче категорию «Инициативы и RFA»');
  await d.click(row.getByTitle('Сохранить категорию'), 'Сохраните категорию');
  // У задачи с подзадачами вместо сохранения открывается выбор охвата.
  const scopePopover = page.locator('.ant-popover:visible', { hasText: 'Сохранить категорию' });
  if (await scopePopover.isVisible({ timeout: 1_500 }).catch(() => false)) {
    await d.click(scopePopover.getByRole('button', { name: 'Только эту задачу' }));
  }
  // Строка уходит из «К разбору», если у задачи не осталось неподтверждённых
  // потомков; иначе она недолго держится как якорь к оставшемуся потомку —
  // категория при этом уже сохранена (проверяем через API).
  let saved = false;
  for (let i = 0; i < 15 && !saved; i++) {
    const res = await page.request.get(`${api}/issues/tree/roots`, { params: { teams: TEAM, tab: 'stack' } });
    const found = (await res.json() as IssueRoot[]).find((r) => r.id === issue.id);
    saved = !found || (found.assigned_category === CATEGORY_CODE && found.category_verified);
    if (!saved) await page.waitForTimeout(400);
  }
  expect(saved, `Категория «${CATEGORY}» не сохранилась для ${issue.key}`).toBeTruthy();
  if ((await row.count()) === 0) {
    await expect(row).toHaveCount(0);
  }
  await page.mouse.move(700, 120);

  // Очередь «Инициативы» — задача сразу переехала туда.
  const initiativesCard = page.locator('[data-tour="categories-queues"] .category-queue-card', { hasText: 'Инициативы' });
  await d.click(initiativesCard, 'Задача сразу перешла в очередь «Инициативы»');
  const initiativesRow = table.locator('tbody tr', { hasText: issue.key });
  await expect(initiativesRow).toBeVisible({ timeout: 15_000 });
  await d.show(initiativesRow);
  await d.pause(1800);

  await ensureIncludedInPlanning(page, api, issue.key);

  await d.caption('Отнесли к инициативам — задача сама появилась в целевых задачах');
  await d.click(page.locator('.side-item', { hasText: 'Целевые задачи' }));
  const activePane = page.locator('[data-tour="backlog-tabs"] .ant-tabs-tabpane-active');
  await expect(activePane.locator('tbody tr.ant-table-row').first()).toBeVisible({ timeout: 15_000 });
  await d.caption('На «Активных» — задачи уже утверждённого плана квартала');
  await d.show(activePane);
  await d.pause(1400);

  const backlogPane = page.locator('[data-tour="backlog-tabs"] .ant-tabs-tabpane-active');
  await d.click(
    page.locator('[data-tour="backlog-tabs"] .ant-tabs-tab', { hasText: 'Бэклог' }),
    'А наша инициатива — в «Бэклоге», среди кандидатов на планирование',
  );
  const backlogRow = backlogPane.locator('tbody tr', { hasText: issue.key });
  await expect(backlogRow).toBeVisible({ timeout: 20_000 });
  await d.show(backlogRow);
  await d.pause(2200);

  const allocRes = await page.request.get(`${api}/planning/scenarios/${scenarioId}/allocations`);
  expect(allocRes.ok()).toBeTruthy();
  const allocs = (await allocRes.json()) as Alloc[];
  const backlogListRes = await page.request.get(`${api}/backlog`, { params: { view: 'active', teams: TEAM } });
  const backlogList = (await backlogListRes.json()) as BacklogListItem[];
  const backlogItem = backlogList.find((it) => it.jira_key === issue.key);
  expect(backlogItem, `Задача ${issue.key} не найдена в бэклоге`).toBeTruthy();
  const alloc = allocs.find((a) => a.backlog_item_id === backlogItem!.id);
  expect(alloc, `Нет allocation для ${issue.key} в черновике сценария`).toBeTruthy();

  await d.caption('…и в черновике сценария квартала');
  await d.click(page.locator('.side-item', { hasText: 'Сценарии' }));
  await pickOption(
    d, page,
    page.locator('[data-tour="planning-scenario-select"]'),
    scenarioName,
    'Выберите нужный черновик сценария',
  );

  const candidateRow = page.locator(`[data-flip-wrapper][data-alloc-id="${alloc!.id}"] .backlog-row`);
  await expect(candidateRow).toBeVisible({ timeout: 20_000 });
  await d.caption('Задача уже здесь — среди кандидатов квартала');
  await d.show(candidateRow);
  await d.pause(2000);

  const roleCard = page.locator('.ant-card', { hasText: 'Ресурс по ролям' });
  await d.caption('Отметить галочкой — и её часы лягут в план команды');
  await d.show(roleCard);
  await d.pause(1600);

  await d.caption('Готово', 2200);
  await d.save('category-to-scenario');
});
