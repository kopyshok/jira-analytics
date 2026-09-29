// Глава 4 «Личная вовлечённость и нормированные работы»: страница сценария →
// «Вовлечённость» → значения по ролям в процентах → раздел «Сотрудники» →
// запись конкретному человеку на квартал: своя вовлечённость и свои проценты
// нормированных работ → запись в списке.
import { expect, type Locator, type Page, test } from '@playwright/test';
import { Director } from '../director.ts';
import { CHAPTERS } from './chapters.ts';
import { apiUrl, chapterTitle, releaseFrame, saveClip } from './common.ts';

const TEAM = 'Команда Альфа';
/** Своя вовлечённость сотрудника в ролике. */
const INVOLVEMENT = 50;
/** Свой процент сопровождения (у роли меньше). */
const SUPPORT = 30;

type Scenario = { id: string; team: string | null; year: number; quarter: string };
type ResourceEmployee = { employee_id: string; display_name: string; role: string | null; shared_with?: string[] };
type WorkType = { id: string; label: string; subtracts_from_pool: boolean };
type Personal = { id: string; employee_id: string; effective_year: number; effective_quarter: number };

releaseFrame();

let scenarioId = '';
let year = 0;
let quarter = 0;
let person: ResourceEmployee | undefined;
let support: WorkType | undefined;

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

  // Самый свежий сценарий демо-команды (статус не важен: панель одна для любого).
  const scenarios = await getJson<Scenario[]>(`${api}/planning/scenarios`);
  const scenario = scenarios
    .filter((s) => s.team === TEAM && s.year && s.quarter)
    .sort((a, b) => b.year - a.year || b.quarter.localeCompare(a.quarter))[0];
  expect(scenario, `нет сценария команды ${TEAM}`).toBeTruthy();
  scenarioId = scenario.id;
  year = scenario.year;
  quarter = Number(scenario.quarter.replace('Q', ''));

  // Разработчик только этой команды — без оговорок про общий ресурс.
  const resource = await getJson<{ employees: ResourceEmployee[] }>(`${api}/planning/scenarios/${scenarioId}/resource`);
  person = resource.employees
    .filter((e) => e.role === 'dev' && !(e.shared_with ?? []).length)
    .sort((a, b) => a.display_name.localeCompare(b.display_name))[0];
  expect(person, 'в команде нет разработчика').toBeTruthy();

  const types = await getJson<WorkType[]>(`${api}/mandatory-work-types?is_active=true`);
  support = types.find((w) => w.subtracts_from_pool && /сопровожд/i.test(w.label));
  expect(support, 'нет вида работ «Сопровождение»').toBeTruthy();

  // Запись этого человека на квартал ролика уже могла остаться — снимаем, ролик добавит заново.
  const rows = await getJson<Personal[]>(`${api}/planning/personal-settings?team=${encodeURIComponent(TEAM)}`);
  for (const r of rows.filter(
    (x) => x.employee_id === person!.employee_id && x.effective_year === year && x.effective_quarter === quarter,
  )) {
    expect((await request.delete(`${api}/planning/personal-settings/${r.id}`)).ok()).toBeTruthy();
  }
  await request.dispose();
});

/**
 * Короткий клик для второстепенных шагов (пункт списка, поле ввода): курсор
 * и нажатие видны, но без рамки и долгих пауз режиссёра — глава и так плотная.
 */
async function tap(page: Page, target: Locator): Promise<void> {
  const box = await target.boundingBox();
  if (!box) throw new Error(`Элемент не виден на экране: ${target}`);
  await page.evaluate((at) => window.__director?.move(at.x, at.y), {
    x: box.x + box.width / 2,
    y: box.y + box.height / 2,
  });
  await page.waitForTimeout(650);
  await page.evaluate(() => window.__director?.press());
  await page.waitForTimeout(120);
  await target.click();
  await page.waitForTimeout(250);
}

/** Увести курсор под поле ввода справа, чтобы не закрывал набираемые цифры. */
async function aside(page: Page, target: Locator): Promise<void> {
  const box = await target.boundingBox();
  if (!box) return;
  await page.evaluate((at) => window.__director?.move(at.x, at.y), {
    x: box.x + box.width + 24,
    y: box.y + box.height + 14,
  });
}

test('04-personal-involvement', async ({ page }) => {
  const name = person!.display_name;
  const surname = name.split(' ')[0];

  const d = new Director(page);
  await d.install();
  await d.open(`/planning?scenario=${scenarioId}`, chapterTitle(4, CHAPTERS[3]));

  const openBtn = page.locator('[data-tour="planning-involvement"]');
  await expect(openBtn).toBeVisible({ timeout: 60_000 });
  await expect(page.locator('[data-tour="planning-capacity-panel"]')).toBeVisible({ timeout: 60_000 });
  await d.pause(1200);

  await d.click(openBtn, 'На странице сценария откройте «Вовлечённость»');
  const drawer = page.locator('.ant-drawer-open .ant-drawer-section');
  await expect(drawer).toBeVisible();
  const section = (title: string) =>
    drawer.locator('h5', { hasText: new RegExp(`^${title}$`) }).locator('xpath=..');
  const roles = section('По ролям команды');
  const people = section('Сотрудники');
  await expect(roles.locator('.ant-table-row').first()).toBeVisible();
  await page.mouse.move(700, 120);

  await d.caption('Значения по ролям — в процентах, их можно исправить');
  await d.show(roles.locator('.ant-table'));
  await d.pause(900);

  await d.caption('Новый раздел «Сотрудники» — настройка одного человека');
  await d.show(people);
  await d.pause(700);
  await d.click(people.getByRole('button', { name: 'Добавить' }));
  const modal = page.locator('.ant-modal:visible');
  await expect(modal).toBeVisible();
  // Окно появляется с увеличением: рамку ставим, когда оно встало на место.
  await d.pause(450);
  const dropdown = page.locator('.ant-select-dropdown:visible');

  const employeeSelect = modal.locator('.ant-select', { has: page.locator('#personal-setting-employee') });
  await d.click(employeeSelect, 'Кому правило роли не подходит — выберите человека');
  await page.keyboard.type(surname, { delay: 100 });
  await expect(dropdown.locator('.ant-select-item-option-active', { hasText: name })).toBeVisible();
  await d.pause(300);
  await page.keyboard.press('Enter');
  await expect(employeeSelect).toContainText(name);

  const yearInput = modal.locator('#personal-setting-year');
  if ((await yearInput.inputValue()) !== String(year)) await yearInput.fill(String(year));
  const quarterSelect = modal.locator('.ant-select', { has: page.locator('#personal-setting-quarter') });
  await d.caption('Квартал, с которого действует запись');
  await tap(page, quarterSelect);
  await tap(page, dropdown.locator('.ant-select-item-option', { hasText: `Q${quarter}` }).first());
  await expect(quarterSelect).toContainText(`Q${quarter}`);

  const involvement = modal.locator('#personal-setting-involvement');
  await d.caption(`Своя вовлечённость — например, ${INVOLVEMENT}%`);
  await tap(page, involvement);
  await aside(page, involvement);
  await involvement.pressSequentially(String(INVOLVEMENT), { delay: 120 });
  await d.pause(300);

  await d.caption('И свои проценты нормированных работ');
  await tap(page, modal.getByRole('switch', { name: 'Нормированные работы: по правилам роли или свои' }));
  const supportInput = modal.locator(`[id="personal-setting-normed-${support!.id}"]`);
  await expect(supportInput).toBeVisible();
  await d.pause(400);
  await tap(page, supportInput);
  await aside(page, supportInput);
  await supportInput.press('Control+A');
  await supportInput.pressSequentially(String(SUPPORT), { delay: 120 });
  await d.pause(400);

  await d.click(modal.getByRole('button', { name: 'Добавить' }), 'Сохраните запись');
  await expect(page.locator('.ant-modal:visible')).toHaveCount(0);
  const row = people.locator('.ant-table-row', { hasText: name });
  await expect(row).toBeVisible();
  await expect(row).toContainText(`${INVOLVEMENT}%`);
  await expect(row).toContainText(`${support!.label} ${SUPPORT}%`);
  await page.mouse.move(700, 120);

  await d.caption('Личная настройка главнее задачи и правил роли');
  await d.show(row);
  await d.pause(3000);
  await saveClip(page, '04-personal-involvement');

  // Запись меняет раскладку и запас сотрудника — следующим главам общего прогона
  // она не нужна: снимаем.
  const request = page.context().request;
  const rows: Personal[] = await (
    await request.get(`${apiUrl()}/planning/personal-settings?team=${encodeURIComponent(TEAM)}`)
  ).json();
  for (const r of rows.filter(
    (x) => x.employee_id === person!.employee_id && x.effective_year === year && x.effective_quarter === quarter,
  )) {
    expect((await request.delete(`${apiUrl()}/planning/personal-settings/${r.id}`)).ok()).toBeTruthy();
  }
});
