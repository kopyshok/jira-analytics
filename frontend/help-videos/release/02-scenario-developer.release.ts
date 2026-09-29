// Глава 2 «Разработчик задачи в сценарии»: колонка «Исполнитель» стала «Аналитиком»,
// рядом — новая колонка «Разработчик»; выбранному разработчику засчитываются часы
// разработки, и он не может быть аналитиком той же задачи.
import { expect, test } from '@playwright/test';
import { Director } from '../director.ts';
import { chapterTitle, saveClip, releaseFrame } from './common.ts';

const TEAM = 'Команда Альфа';

type Scenario = { id: string; team: string | null; year: number; quarter: string; status: string };
type Alloc = {
  id: string;
  backlog_item_id: string;
  included: boolean;
  estimate_dev_hours: number | null;
  override_estimate_dev_hours: number | null;
  assignee_employee_id: string | null;
  developer_employee_id: string | null;
};
type CandidateGroup = { key: string; employees: { employee_id: string; display_name: string; role: string | null }[] };

releaseFrame();

let scenarioId = '';
let allocId = '';
let dev: { display_name: string } | undefined;
let wasApproved = false;

// Данные готовим до открытия окна: запись идёт с момента его создания,
// и подготовка внутри теста дала бы секунды тёмного экрана в начале ролика.
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

  // Шапка — на демо-команду (предыдущие главы могли переключить).
  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();

  // Самый свежий сценарий демо-команды; утверждённый возвращаем в черновик —
  // выбирать людей можно только в черновике (копия базы одноразовая).
  const scenarios = await getJson<Scenario[]>(`${api}/planning/scenarios`);
  const scenario = scenarios
    .filter((s) => s.team === TEAM)
    .sort((a, b) => b.year - a.year || b.quarter.localeCompare(a.quarter))[0];
  expect(scenario, `нет сценария команды ${TEAM}`).toBeTruthy();
  wasApproved = scenario.status === 'approved';
  if (scenario.status !== 'draft') {
    const res = await request.post(`${api}/planning/scenarios/${scenario.id}/revert-to-draft`);
    expect(res.ok()).toBeTruthy();
  }

  // Строка: включена, есть часы разработки, аналитик выбран. Разработчика в ней
  // снимаем заранее — в ролике его выбирают заново (обычно того же).
  const allocs = await getJson<Alloc[]>(`${api}/planning/scenarios/${scenario.id}/allocations`);
  const alloc = allocs.find(
    (a) => a.included && (a.override_estimate_dev_hours ?? a.estimate_dev_hours ?? 0) > 0 && a.assignee_employee_id,
  );
  expect(alloc, 'нет подходящей строки сценария').toBeTruthy();
  const prevDev = alloc!.developer_employee_id;
  if (prevDev) {
    const res = await request.patch(
      `${api}/planning/scenarios/${scenario.id}/allocations/${alloc!.id}/developer`,
      { data: { developer_employee_id: null } },
    );
    expect(res.ok()).toBeTruthy();
  }

  // Разработчик из своей команды — он есть в блоке «По сотрудникам».
  const groups = await getJson<CandidateGroup[]>(
    `${api}/planning/scenarios/${scenario.id}/assignee-candidates?backlog_item_id=${alloc!.backlog_item_id}&phase=dev`,
  );
  const teamDevs =
    groups
      .find((g) => g.key === 'team')
      ?.employees.filter((e) => e.role === 'dev' && e.employee_id !== alloc!.assignee_employee_id) ?? [];
  dev = teamDevs.find((e) => e.employee_id === prevDev) ?? teamDevs[0];
  expect(dev, 'в команде нет разработчика').toBeTruthy();
  scenarioId = scenario.id;
  allocId = alloc!.id;
  await request.dispose();
});

// Сценарий снова утверждён: ресурсный план следующих глав показывает только утверждённые.
test.afterAll(async ({ playwright }, testInfo) => {
  if (!wasApproved) return;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  expect((await request.post(`${api}/planning/scenarios/${scenarioId}/approve`)).ok()).toBeTruthy();
  await request.dispose();
});

test('02-scenario-developer', async ({ page }) => {
  const surname = dev!.display_name.split(' ')[0];

  const d = new Director(page);
  await d.install();
  await d.open(`/planning?scenario=${scenarioId}`, chapterTitle(2, 'Разработчик задачи в сценарии'));

  const backlog = page.locator('.ant-card', { has: page.locator('.ant-card-head', { hasText: 'Элементы бэклога' }) });
  const row = page.locator(`[data-alloc-id="${allocId}"]`);
  await expect(row).toBeVisible({ timeout: 60_000 });
  await d.pause(2000);

  // Таблица сценария — к верху экрана: шапка колонок не должна прятаться под подписью.
  await backlog.evaluate((el) => el.scrollIntoView({ block: 'start', behavior: 'smooth' }));
  await d.pause(900);

  await d.caption('Колонка «Исполнитель» теперь называется «Аналитик»');
  await d.show(backlog.locator('span', { hasText: /^\s*Аналитик\s*$/ }).first());
  await d.pause(1200);

  await d.caption('Рядом — новая колонка «Разработчик»');
  await d.show(backlog.locator('span', { hasText: /^\s*Разработчик\s*$/ }).first());
  await d.pause(1200);

  const cells = row.locator(':scope > div > div > .ant-select');
  const analystSelect = cells.nth(0);
  const devSelect = cells.nth(1);
  await d.click(devSelect, 'Если разработчик известен заранее — выберите его');
  const dropdown = page.locator('.ant-select-dropdown:visible');
  await expect(dropdown.locator('.ant-select-item-option').first()).toBeVisible({ timeout: 20_000 });
  await d.caption('В списке — роль и загрузка; можно найти по фамилии');
  await page.keyboard.type(surname, { delay: 110 });
  await d.pause(700);
  await d.click(dropdown.locator('.ant-select-item-option', { hasText: dev!.display_name }).first());
  await expect(devSelect).toContainText(dev!.display_name);
  await page.mouse.move(700, 120);

  await d.caption('Разработчик задачи назначен');
  await d.show(devSelect);
  await d.pause(1200);

  // Имя → строка имени → шапка → блок сотрудника целиком (с полосой загрузки).
  const person = page
    .locator('.ant-card', { has: page.locator('.ant-card-head', { hasText: 'По сотрудникам' }) })
    .getByText(dev!.display_name, { exact: true })
    .locator('xpath=../../..');
  await d.caption('Часы разработки засчитаны разработчику в блоке «По сотрудникам»');
  await d.show(person);
  await d.pause(1600);

  await d.click(analystSelect, 'Этого же человека аналитиком задачи назначить нельзя');
  await expect(dropdown.locator('.ant-select-item-option').first()).toBeVisible({ timeout: 20_000 });
  await page.keyboard.type(surname, { delay: 110 });
  const busy = dropdown.locator('.ant-select-item-option-disabled', { hasText: 'уже разработчик этой задачи' });
  await expect(busy).toBeVisible();
  await d.caption('Один человек — одна роль в задаче');
  await d.show(busy);
  await d.pause(1600);
  await page.keyboard.press('Escape');
  await page.mouse.move(700, 120);

  await d.caption('Ресурсный план отдаст разработчику фазу «Разработка»');
  await d.show(devSelect);
  await d.pause(2600);
  await saveClip(page, '02-scenario-developer');
});
