// Ролик «Как задать нормированные работы и вовлечённость»: черновик на свободный
// квартал (подготовлен в beforeAll) → вкладка «Правила» — новое правило вручную →
// «Сохранить» → «На бэклог» уменьшился → панель «Вовлечённость»: справочник по
// ролям и личная настройка сотрудника → ресурс пересчитался.
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';

interface ScenarioListItem {
  year: number | null;
  quarter: string | null;
  team: string | null;
}
interface WorkTypeItem {
  id: string;
  label: string;
  subtracts_from_pool: boolean;
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
interface ResourceEmployeeLite {
  employee_id: string;
  display_name: string;
  role: string | null;
}
interface PersonalSettingRow {
  id: string;
  employee_id: string;
  effective_year: number;
  effective_quarter: number;
}

let scenarioId = '';
let freeYear = 0;
let freeQuarter = 0;
let workType: WorkTypeItem | null = null;
let analystLabel = 'Аналитик';
let devEmployee: ResourceEmployeeLite | undefined;
// Личная настройка сотрудника создаётся на камеру — id нужен только для очистки.
let personalSettingId: string | null = null;

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const getJson = async <T,>(url: string, params?: Record<string, string>): Promise<T> => {
    const res = await request.get(url, params ? { params } : undefined);
    expect(res.ok(), url).toBeTruthy();
    return (await res.json()) as T;
  };

  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();

  // Первый квартал, для которого у команды ещё нет сценария — детерминировано
  // в любой день, не зависит от состава демо-базы.
  const list = await getJson<ScenarioListItem[]>(`${api}/planning/scenarios`, { teams: TEAM });
  const keys = list
    .filter((s) => s.team === TEAM && s.year != null && s.quarter != null)
    .map((s) => (s.year as number) * 4 + (Number((s.quarter as string).replace('Q', '')) - 1));
  const now = new Date();
  const currentKey = now.getFullYear() * 4 + Math.floor(now.getMonth() / 3);
  const nextKey = Math.max(currentKey, ...keys) + 1;
  freeYear = Math.floor(nextKey / 4);
  freeQuarter = (nextKey % 4) + 1;

  const created = await request.post(`${api}/planning/scenarios`, {
    data: { name: `${freeYear} Q${freeQuarter} ${TEAM}`, year: freeYear, quarter: freeQuarter, team: TEAM },
  });
  expect(created.ok()).toBeTruthy();
  scenarioId = (await created.json()).id;

  // Пара включённых инициатив — иначе панель ресурса пуста и правку не на чем показать.
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

  const workTypes = await getJson<WorkTypeItem[]>(`${api}/mandatory-work-types`, { is_active: 'true' });
  expect(workTypes.length, 'нет ни одного вида работ').toBeGreaterThan(0);
  workType = workTypes.find((w) => w.subtracts_from_pool) ?? workTypes[0];

  const roles = await getJson<RoleItem[]>(`${api}/roles`);
  analystLabel = roles.find((r) => r.code === 'analyst')?.label ?? analystLabel;

  const resource = await getJson<{ employees: ResourceEmployeeLite[] }>(
    `${api}/planning/scenarios/${scenarioId}/resource`,
  );
  devEmployee = resource.employees.find((e) => e.role === 'dev');
  expect(devEmployee, 'в команде нет разработчика').toBeTruthy();

  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  // Справочник вовлечённости и личные настройки — общие для всех роликов
  // прогона: своё удаляем полностью, чтобы не мешать остальным.
  if (personalSettingId) {
    await request.delete(`${api}/planning/personal-settings/${personalSettingId}`);
  }
  if (scenarioId) {
    await request.delete(`${api}/planning/scenarios/${scenarioId}`);
  }
  await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } });
  await request.dispose();
});

test('scenario-rules', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  const api = String(test.info().config.metadata.backendUrl);

  await d.open(`/planning?scenario=${scenarioId}`, 'Как задать нормированные работы и вовлечённость');
  await expect(page.getByText('Черновик')).toBeVisible({ timeout: 15_000 });
  await expect(page.locator('[data-tour="planning-capacity-panel"]')).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  // === Новое правило нормированных работ ===
  await d.click(page.locator('[data-tour="planning-tab-rules"]'), 'Откройте вкладку «Правила»');
  const rulesCard = page.locator('[data-tour="planning-rules-card"]');
  await expect(rulesCard).toBeVisible();

  const roleCard = page.locator('.ant-card', { hasText: 'Ресурс по ролям' });
  await d.caption('Справа — ресурс на инициативы до правки');
  await d.show(roleCard);
  await d.pause(1000);
  const beforeRuleText = await roleCard.innerText();

  await d.click(rulesCard.getByRole('button', { name: 'Добавить правило' }), 'Добавьте правило нормированных работ');
  const newRow = rulesCard.locator('tbody tr.ant-table-row').last();
  await expect(newRow).toBeVisible();

  await d.click(newRow.locator('.ant-select').first(), 'Укажите роль');
  await d.click(
    page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: analystLabel }),
  );

  await d.click(newRow.locator('.ant-select').nth(1), 'Укажите вид работ');
  await d.click(
    page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: workType!.label }),
  );

  const percentInput = newRow.locator('.ant-input-number-input');
  await d.click(percentInput, 'Задайте процент от нормы');
  await percentInput.press('Control+A');
  await percentInput.pressSequentially('40', { delay: 90 });
  await d.pause(400);

  await d.click(rulesCard.getByRole('button', { name: 'Сохранить' }), 'Сохраните правило');
  await expect(rulesCard.getByRole('button', { name: 'Сбросить' })).toHaveCount(0, { timeout: 10_000 });

  await d.caption('Нормированные работы уменьшают часы на задачи');
  await d.show(roleCard);
  await d.pause(1200);
  await expect.poll(() => roleCard.innerText()).not.toBe(beforeRuleText);
  await d.pause(400);

  // === Панель «Вовлечённость и нормированные работы» ===
  await d.click(page.locator('[data-tour="planning-involvement"]'), 'Откройте панель «Вовлечённость»');
  const drawer = page.locator('.ant-drawer-open');
  await expect(drawer).toBeVisible();
  await d.pause(400);

  await d.caption('Справочник вовлечённости по ролям команды');
  await d.show(drawer.getByRole('heading', { name: 'По ролям команды' }));
  await d.pause(1400);

  await d.caption('«Сотрудники» — личная настройка, если общее правило не подходит');
  await d.show(drawer.getByRole('heading', { name: 'Сотрудники' }));
  await d.pause(1400);

  const beforeInvolvementText = await roleCard.innerText();

  await d.click(drawer.locator('[data-testid="involvement-employee-add"]'), 'Нажмите «Добавить»');
  const empModal = page.locator('.ant-modal', { hasText: 'Добавить сотрудника' });
  await expect(empModal).toBeVisible();

  const surname = devEmployee!.display_name.split(' ')[0];
  const employeeSelect = empModal.locator('.ant-select').first();
  await d.click(employeeSelect, 'Выберите разработчика');
  const dropdown = page.locator('.ant-select-dropdown:visible');
  await expect(dropdown.locator('.ant-select-item-option').first()).toBeVisible();
  await page.keyboard.type(surname, { delay: 100 });
  await d.click(dropdown.locator('.ant-select-item-option', { hasText: devEmployee!.display_name }).first());

  const yearInput = empModal.locator('#personal-setting-year');
  await yearInput.click();
  await yearInput.press('Control+A');
  await yearInput.pressSequentially(String(freeYear), { delay: 80 });

  const quarterSelect = empModal.locator('#personal-setting-quarter');
  await d.click(quarterSelect);
  await d.click(
    page.locator('.ant-select-dropdown:visible .ant-select-item-option', {
      hasText: new RegExp(`^Q${freeQuarter}$`),
    }),
  );

  const involvementInput = empModal.locator('#personal-setting-involvement');
  await d.click(involvementInput, 'Задайте вовлечённость и «свои» проценты');
  await involvementInput.pressSequentially('80', { delay: 90 });

  await d.click(empModal.getByRole('switch', { name: 'Нормированные работы: по правилам роли или свои' }));
  const normedInput = empModal.locator(`#personal-setting-normed-${workType!.id}`);
  await d.click(normedInput);
  await normedInput.press('Control+A');
  await normedInput.pressSequentially('20', { delay: 90 });
  await d.pause(400);

  await d.click(empModal.getByRole('button', { name: 'Добавить' }), 'Сохраните запись');
  await expect(page.getByText(/Чтобы раскладка учла изменение/)).toBeVisible({ timeout: 10_000 });

  const personalRes = await page.request.get(`${api}/api/v1/planning/personal-settings`, {
    params: { team: TEAM },
  });
  expect(personalRes.ok()).toBeTruthy();
  const personalRows: PersonalSettingRow[] = await personalRes.json();
  const createdRow = personalRows.find(
    (r) => r.employee_id === devEmployee!.employee_id && r.effective_year === freeYear && r.effective_quarter === freeQuarter,
  );
  personalSettingId = createdRow?.id ?? null;

  await d.caption('Раскладку нужно пересчитать кнопкой «Распределить» в ресурсном плане', 2400);

  await d.click(page.locator('.ant-drawer-close'), 'Закройте панель');
  await expect(drawer).toBeHidden();
  await page.mouse.move(700, 120);

  await d.caption('Вовлечённость удлиняет фазы в ресурсном плане, а ресурс сценария уже пересчитан');
  await d.show(roleCard);
  await d.pause(1600);
  await expect.poll(() => roleCard.innerText()).not.toBe(beforeInvolvementText);

  await d.caption('Готово', 2200);
  await d.save('scenario-rules');
});
