// Ролик «Как завести вид нормированных работ»: «Настройки» → «Виды работ» — новый вид
// («Вычитается из пула») → «Категории работ»: категория привязана к виду → «Сценарии»,
// вкладка «Правила»: процент роли по новому виду → ресурс на инициативы уменьшился.
// От имени демо-администратора. В конце всё созданное убрано, привязка категории возвращена.
import { expect, test } from '@playwright/test';
import { ADMIN_STATE } from './admin.ts';
import { Director } from './director.ts';

test.use({ storageState: ADMIN_STATE });

const TEAM = 'Команда Альфа';
const NEW_CODE = 'training_dev';
const NEW_LABEL = 'Обучение и развитие';
/** Категория, которую привяжем к новому виду (прежняя привязка вернётся в конце). */
const CATEGORY_LABEL = 'Внутренние коммуникации команд';
const CATEGORY_CODE = 'internal_communications';

interface ScenarioListItem {
  year: number | null;
  quarter: string | null;
  team: string | null;
}
interface WorkTypeItem {
  id: string;
  code: string;
  label: string;
}
interface CategoryItem {
  id: string;
  code: string;
  label: string;
  color: string | null;
  sort_order: number;
  work_type_id: string | null;
}
interface AllocationItem {
  id: string;
  estimate_analyst_hours: number | null;
  estimate_dev_hours: number | null;
  estimate_qa_hours: number | null;
}
interface RoleItem {
  code: string;
  label: string;
}

let scenarioId = '';
let scenarioName = '';
let analystLabel = 'Аналитик';
let category: CategoryItem | null = null;

async function ctx(playwright: import('@playwright/test').PlaywrightWorkerArgs['playwright'], testInfo: import('@playwright/test').TestInfo) {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({ storageState: ADMIN_STATE });
  return { api, request };
}

test.beforeAll(async ({ playwright }, testInfo) => {
  const { api, request } = await ctx(playwright, testInfo);
  const getJson = async <T,>(url: string, params?: Record<string, string>): Promise<T> => {
    const res = await request.get(url, params ? { params } : undefined);
    expect(res.ok(), url).toBeTruthy();
    return (await res.json()) as T;
  };

  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();

  // Остатки прошлой съёмки: сначала снимаем привязку категории, потом удаляем вид.
  const types = await getJson<WorkTypeItem[]>(`${api}/mandatory-work-types`);
  const stale = types.find((t) => t.code === NEW_CODE);
  if (stale) {
    const cats = await getJson<CategoryItem[]>(`${api}/categories`);
    for (const c of cats.filter((c) => c.work_type_id === stale.id)) {
      await request.put(`${api}/categories/${c.id}`, { data: { work_type_id: null } });
    }
    await request.delete(`${api}/mandatory-work-types/${stale.id}`);
  }

  const cats = await getJson<CategoryItem[]>(`${api}/categories`);
  category = cats.find((c) => c.label === CATEGORY_LABEL) ?? null;
  expect(category, `нет категории «${CATEGORY_LABEL}»`).toBeTruthy();

  // Черновик на свободный квартал: правило можно добавить, не трогая утверждённые.
  const list = await getJson<ScenarioListItem[]>(`${api}/planning/scenarios`, { teams: TEAM });
  const keys = list
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
  expect(created.ok()).toBeTruthy();
  scenarioId = (await created.json()).id;

  // Пара включённых инициатив — иначе панель ресурса пуста.
  const allocs = await getJson<AllocationItem[]>(`${api}/planning/scenarios/${scenarioId}/allocations`);
  const withHours = allocs
    .filter((a) => (a.estimate_analyst_hours ?? 0) + (a.estimate_dev_hours ?? 0) + (a.estimate_qa_hours ?? 0) > 0)
    .slice(0, 2);
  expect(withHours.length, 'в бэклоге нет задач с часами').toBeGreaterThan(0);
  for (const a of withHours) {
    const res = await request.patch(`${api}/planning/scenarios/${scenarioId}/allocations/${a.id}`, {
      data: { included: true, lift: true },
    });
    expect(res.ok()).toBeTruthy();
  }

  const roles = await getJson<RoleItem[]>(`${api}/roles`);
  analystLabel = roles.find((r) => r.code === 'analyst')?.label ?? analystLabel;
  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  const { api, request } = await ctx(playwright, testInfo);
  // Порядок важен: категория, сценарий с правилом, затем сам вид.
  if (category) {
    await request.put(`${api}/categories/${category.id}`, { data: { work_type_id: category.work_type_id } });
  }
  if (scenarioId) await request.delete(`${api}/planning/scenarios/${scenarioId}`);
  const types = (await (await request.get(`${api}/mandatory-work-types`)).json()) as WorkTypeItem[];
  const created = types.find((t) => t.code === NEW_CODE);
  if (created) await request.delete(`${api}/mandatory-work-types/${created.id}`);
  await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } });
  await request.dispose();
});

test('settings-work-types', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  await d.open('/settings#worktypes', 'Как завести вид нормированных работ');
  const addButton = page.getByRole('button', { name: 'Добавить вид работ' });
  await expect(addButton).toBeVisible({ timeout: 20_000 });
  await expect(page.locator('.ant-table-row').first()).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  const menuItem = (label: string) => page.locator('.ant-menu-item', { hasText: label });

  await d.caption('«Настройки», экран «Виды работ» — справочник нормированных работ');
  await d.show(menuItem('Виды работ'));
  await d.pause(1500);

  await d.click(addButton, 'Нажмите «Добавить вид работ»');
  const modal = page.locator('.ant-modal', { hasText: 'Новый вид работ' });
  await expect(modal).toBeVisible();
  await d.type(modal.locator('#code'), NEW_CODE, 'Введите код латиницей');
  await d.type(modal.locator('#label'), NEW_LABEL, 'И название вида');
  await d.caption('«Вычитается из пула» включено — вид уменьшит время на проекты');
  await d.show(modal.locator('.ant-form-item', { hasText: 'Вычитается из пула' }));
  await d.pause(1500);
  await d.click(modal.getByRole('button', { name: 'Сохранить' }), 'Сохраните');
  await expect(modal).toBeHidden();
  await page.mouse.move(1300, 120);

  const newRow = page.locator('tr.ant-table-row', { hasText: NEW_LABEL });
  await expect(newRow).toBeVisible();
  await d.caption('Новый вид появился в справочнике');
  await d.show(newRow);
  await d.pause(1500);

  // === Категория → вид ===
  await d.waitVoice();
  await d.click(menuItem('Категории работ'), 'Теперь привяжем к виду категорию');
  const catRow = page.locator('tr.ant-table-row', { hasText: CATEGORY_CODE });
  await expect(catRow).toBeVisible({ timeout: 15_000 });
  await d.caption('В колонке «Вид работ» выберите новый вид');
  await d.show(catRow);
  await d.pause(800);
  await d.click(catRow.locator('.ant-select'));
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: NEW_LABEL }));
  await expect(catRow.locator('.ant-select')).toContainText(NEW_LABEL);
  await page.mouse.move(1300, 120);
  await d.caption('Часы задач этой категории теперь идут в новый вид');
  await d.show(catRow);
  await d.pause(1800);

  // === Правила сценария ===
  await d.waitVoice();
  await d.click(page.locator('.side-item', { hasText: 'Сценарии' }), 'Дальше — «Сценарии»');
  await d.click(page.locator('[data-tour="planning-scenario-select"]'), 'Откройте черновик сценария');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: scenarioName }));
  await expect(page.locator('[data-tour="planning-capacity-panel"]')).toBeVisible({ timeout: 20_000 });
  await d.click(page.locator('[data-tour="planning-tab-rules"]'), 'Вкладка «Правила»');
  const rulesCard = page.locator('[data-tour="planning-rules-card"]');
  await expect(rulesCard).toBeVisible();

  const roleCard = page.locator('.ant-card', { hasText: 'Ресурс по ролям' });
  const beforeText = await roleCard.innerText();

  await d.click(rulesCard.getByRole('button', { name: 'Добавить правило' }), 'Добавьте правило');
  const row = rulesCard.locator('tbody tr.ant-table-row').last();
  await expect(row).toBeVisible();
  await d.click(row.locator('.ant-select').first(), 'Укажите роль');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: analystLabel }));
  await d.click(row.locator('.ant-select').nth(1), 'Выберите новый вид работ');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: NEW_LABEL }));
  const percent = row.locator('.ant-input-number-input');
  await d.click(percent, 'И процент от нормы роли');
  await percent.press('Control+A');
  await percent.pressSequentially('15', { delay: 90 });
  await d.pause(400);
  await d.click(rulesCard.getByRole('button', { name: 'Сохранить' }), 'Сохраните правило');
  await expect(rulesCard.getByRole('button', { name: 'Сбросить' })).toHaveCount(0, { timeout: 10_000 });
  await page.mouse.move(700, 120);

  await expect.poll(() => roleCard.innerText()).not.toBe(beforeText);
  await d.caption('Процент роли по новому виду уменьшил ресурс на инициативы');
  await d.show(roleCard);
  await d.pause(2000);

  await d.caption('Готово', 2200);
  await d.save('settings-work-types');
});
