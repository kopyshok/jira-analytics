// Ролик «Как назначить разработчика в сценарии»: утверждённый сценарий квартала
// возвращаем в черновик → в строке назначаем аналитика и разработчика (группы
// «Из Jira / Моя команда / Другие команды», загрузка %, взаимная блокировка) →
// «Утвердить» → «Диаграмма» → «Распределить» → разработчик сам встал на фазу
// «Разработка» этой же задачи.
import { expect, test } from '@playwright/test';
import { Director } from './director.ts';
import { phaseBar } from './rp-setup.ts';

const TEAM = 'Команда Альфа';

interface ScenarioItem {
  id: string;
  year: number | null;
  quarter: string | null;
  team: string | null;
  status: 'draft' | 'approved';
}

interface AllocationItem {
  id: string;
  backlog_item_id: string;
  included: boolean;
  estimate_dev_hours: number | null;
  override_estimate_dev_hours: number | null;
  assignee_employee_id: string | null;
  developer_employee_id: string | null;
}

type Candidate = { employee_id: string; display_name: string; role: string | null };
type CandidateGroup = { key: string; label: string; employees: Candidate[] };

let scenarioId = '';
let allocId = '';
let backlogItemId = '';
let analyst: Candidate | undefined;
let dev: Candidate | undefined;

// Данные готовим до открытия окна: запись идёт с момента создания страницы,
// подготовка внутри теста дала бы секунды тёмного экрана в начале ролика.
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

  const scenarios = await getJson<ScenarioItem[]>(
    `${api}/planning/scenarios?teams=${encodeURIComponent(TEAM)}`,
  );
  const scenario = scenarios.find((s) => s.team === TEAM && s.year === 2026 && s.quarter === 'Q4');
  expect(scenario, `нет сценария Q4 2026 команды ${TEAM}`).toBeTruthy();
  scenarioId = scenario!.id;

  // Выбирать людей можно только в черновике — утверждённый возвращаем на время видео,
  // в конце снова утвердим (см. test ниже).
  if (scenario!.status !== 'draft') {
    const res = await request.post(`${api}/planning/scenarios/${scenarioId}/revert-to-draft`);
    expect(res.ok()).toBeTruthy();
  }

  const allocs = await getJson<AllocationItem[]>(`${api}/planning/scenarios/${scenarioId}/allocations`);
  const alloc = allocs.find(
    (a) => a.included && (a.override_estimate_dev_hours ?? a.estimate_dev_hours ?? 0) > 0,
  );
  expect(alloc, 'нет подходящей строки сценария').toBeTruthy();
  allocId = alloc!.id;
  backlogItemId = alloc!.backlog_item_id;

  // Снимаем текущих аналитика и разработчика строки — в ролике их выбирают заново.
  if (alloc!.assignee_employee_id) {
    const r = await request.patch(
      `${api}/planning/scenarios/${scenarioId}/allocations/${allocId}/assignee`,
      { data: { assignee_employee_id: null } },
    );
    expect(r.ok()).toBeTruthy();
  }
  if (alloc!.developer_employee_id) {
    const r = await request.patch(
      `${api}/planning/scenarios/${scenarioId}/allocations/${allocId}/developer`,
      { data: { developer_employee_id: null } },
    );
    expect(r.ok()).toBeTruthy();
  }

  const analystGroups = await getJson<CandidateGroup[]>(
    `${api}/planning/scenarios/${scenarioId}/assignee-candidates?backlog_item_id=${backlogItemId}&phase=analyst`,
  );
  analyst = (analystGroups.find((g) => g.key === 'team')?.employees ?? [])[0];
  expect(analyst, 'в команде некого назначить аналитиком').toBeTruthy();

  const devGroups = await getJson<CandidateGroup[]>(
    `${api}/planning/scenarios/${scenarioId}/assignee-candidates?backlog_item_id=${backlogItemId}&phase=dev`,
  );
  const devTeam = devGroups.find((g) => g.key === 'team')?.employees ?? [];
  dev =
    devTeam.find((e) => e.role?.toLowerCase() === 'dev' && e.employee_id !== analyst!.employee_id) ??
    devTeam.find((e) => e.employee_id !== analyst!.employee_id);
  expect(dev, 'в команде некого назначить разработчиком').toBeTruthy();

  await request.dispose();
});

test('scenario-developer', async ({ page }) => {
  const analystSurname = analyst!.display_name.split(' ')[0];
  const devSurname = dev!.display_name.split(' ')[0];

  const d = new Director(page);
  await d.install();
  await d.open(`/planning?scenario=${scenarioId}`, 'Как назначить разработчика в сценарии');

  const row = page.locator(`[data-flip-wrapper][data-alloc-id="${allocId}"]`);
  await expect(row).toBeVisible({ timeout: 20_000 });
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  const scenarioCard = page.locator('.ant-card', { hasText: 'Черновик' }).first();
  await d.caption('Сценарий квартала пока в черновике — можно назначать людей');
  await d.show(scenarioCard);
  await d.pause(2200);

  await row.evaluate((el) => el.scrollIntoView({ block: 'center', behavior: 'smooth' }));
  await d.pause(900);

  // Аналитик — первый select ячейки строки, разработчик — второй; у команды
  // без деления на группы колонки «Группа» нет.
  const cells = row.locator(':scope > div > div > .ant-select');
  const analystSelect = cells.nth(0);
  const devSelect = cells.nth(1);
  const dropdown = page.locator('.ant-select-dropdown:visible');

  await d.click(analystSelect, 'Назначьте аналитика — кто ведёт анализ задачи');
  await expect(dropdown.locator('.ant-select-item-option').first()).toBeVisible({ timeout: 20_000 });
  await d.caption('Список поделён на группы: «Из Jira», «Моя команда», «Другие команды»');
  await d.show(dropdown.locator('.rc-virtual-list'));
  await d.pause(2200);
  await page.keyboard.type(analystSurname, { delay: 100 });
  await d.pause(500);
  const analystOption = dropdown.locator('.ant-select-item-option', { hasText: analyst!.display_name });
  await d.caption('У каждого видна роль и загрузка за квартал');
  await d.show(analystOption);
  await d.pause(2000);
  await d.click(analystOption);
  await expect(analystSelect).toContainText(analyst!.display_name);
  await page.mouse.move(700, 120);

  await d.caption('Аналитик назначен — теперь очередь разработчика');
  await d.show(analystSelect);
  await d.pause(2000);

  await d.click(devSelect, 'Теперь — разработчика');
  await expect(dropdown.locator('.ant-select-item-option').first()).toBeVisible({ timeout: 20_000 });
  await page.keyboard.type(analystSurname, { delay: 100 });
  const busy = dropdown.locator('.ant-select-item-option-disabled', { hasText: 'уже аналитик этой задачи' });
  await expect(busy).toBeVisible();
  await d.caption('Тот же человек не может быть и аналитиком, и разработчиком этой задачи');
  await d.show(busy);
  await d.pause(2300);
  await page.keyboard.press('Control+A');
  await page.keyboard.type(devSurname, { delay: 100 });
  await d.pause(500);
  const devOption = dropdown.locator('.ant-select-item-option', { hasText: dev!.display_name });
  await d.click(devOption, 'Выберите разработчика');
  await expect(devSelect).toContainText(dev!.display_name);
  await page.mouse.move(700, 120);

  await d.caption('Разработчик задачи назначен');
  await d.show(devSelect);
  await d.pause(1600);

  const roleCard = page.locator('.ant-card', { hasText: 'Ресурс по ролям' });
  await d.caption('Часы разработки сразу учтены в ресурсе команды');
  await d.show(roleCard);
  await d.pause(2200);

  await d.click(page.locator('[data-tour="planning-approve"]'), 'Нажмите «Утвердить»');
  await expect(page.locator('.ant-badge-status-text', { hasText: 'Утверждён' })).toBeVisible({ timeout: 15_000 });
  await d.pause(900);

  await d.click(page.getByRole('button', { name: 'Диаграмма' }), 'Откройте «Диаграмма»');
  await expect(page.locator('[data-tour="rp-gantt"]')).toBeVisible({ timeout: 20_000 });
  await d.pause(900);

  await d.click(page.locator('[data-tour="rp-distribute"]'), 'Нажмите «Распределить»');
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible({ timeout: 30_000 });
  await d.pause(1400);

  const bar = phaseBar(page, { backlog_item_id: backlogItemId, phase: 'dev', part_number: 1 });
  await expect(bar).toBeVisible({ timeout: 20_000 });
  await d.click(bar, 'Откройте фазу «Разработка» этой задачи');
  const drawer = page.locator('.ant-drawer-open .ant-drawer-section');
  await expect(drawer).toBeVisible();
  const employeeField = drawer
    .locator('.ant-descriptions-row')
    .filter({ has: page.locator('.ant-descriptions-item-label', { hasText: /^Сотрудник$/ }) });
  await expect(employeeField).toContainText(dev!.display_name, { timeout: 15_000 });

  await d.caption('Разработчик из сценария сам стал исполнителем разработки');
  await d.show(employeeField);
  await d.pause(3400);

  await d.caption('Готово', 2200);
  await d.save('scenario-developer');
});
