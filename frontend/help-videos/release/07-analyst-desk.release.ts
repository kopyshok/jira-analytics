// Глава «Стол аналитика: кварталы и дерево задач»: личный стол аналитика по
// ссылке → стрелка «‹» листает на прошлый квартал → в «Мои проекты» проект
// раскрывается деревом → уровни до нижних подзадач → факт часов у задачи.
// Стол выпускается перед съёмкой и отзывается после неё.
import { expect, test } from '@playwright/test';
import { Director } from '../director.ts';
import { apiUrl, chapterTitle, releaseFrame, saveClip } from './common.ts';

const TEAM = 'Команда Альфа';
/** Аналитик демо-команды: в прошлом квартале у неё проекты с глубоким деревом и фактом. */
const ANALYST = 'Акимова Алина';
const WIDGETS = ['my_tasks', 'my_timeline', 'category_breakdown', 'hours_balance'];
const ROMAN = ['', 'I', 'II', 'III', 'IV'];

type Employee = { id: string; display_name: string };
type Node = { key: string | null; title: string | null; fact_hours: number; children?: Node[] };
type Project = { key: string | null; title: string | null; fact_hours: number; children: Node[] };

releaseFrame();

let deskId = '';
let token = '';
let prevLabel = '';
/** Путь по дереву: проект → задача → подзадача, у которой есть свои подзадачи. */
let project: Project | undefined;
let level1: Node | undefined;
let level2: Node | undefined;

const kids = (n: Node | undefined) => n?.children ?? [];

// Данные готовим до открытия окна: иначе в начале ролика — тёмные секунды.
test.beforeAll(async ({ playwright, browser }, testInfo) => {
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

  const employees = await getJson<Employee[]>(`${api}/employees`);
  const analyst = employees.find((e) => e.display_name === ANALYST);
  expect(analyst, `нет сотрудника ${ANALYST}`).toBeTruthy();

  // Новый стол сам отзывает прежний стол сотрудника, если тот остался.
  const created = await request.post(`${api}/work-desks`, {
    data: { employee_id: analyst!.id, enabled_widgets: WIDGETS },
  });
  expect(created.ok()).toBeTruthy();
  ({ id: deskId, token } = (await created.json()) as { id: string; token: string });

  // Прошлый квартал — по тем же часам, что у страницы стола.
  const now = new Date();
  const cur = { year: now.getFullYear(), quarter: Math.floor(now.getMonth() / 3) + 1 };
  const prev = cur.quarter > 1 ? { year: cur.year, quarter: cur.quarter - 1 } : { year: cur.year - 1, quarter: 4 };
  prevLabel = `${ROMAN[prev.quarter]} кв. ${prev.year}`;

  const { projects } = await getJson<{ projects: Project[] }>(
    `${api}/desk/${token}/widget/my_tasks?year=${prev.year}&quarter=${prev.quarter}`,
  );
  // Проект, где у первой задачи (дерево отсортировано по факту) есть подзадачи
  // со своими подзадачами — видно все уровни; при равенстве — больше факта.
  project = projects
    .filter((p) => p.title && kids(kids(p.children[0])[0]).length > 0)
    .sort((a, b) => b.fact_hours - a.fact_hours)[0];
  expect(project, `у ${ANALYST} нет проекта с деревом в три уровня за ${prevLabel}`).toBeTruthy();
  level1 = project!.children[0];
  level2 = kids(level1)[0];
  expect(level1.key && level2?.key && level1.fact_hours > 0).toBeTruthy();
  await request.dispose();

  // Прогрев страницы стола: первая загрузка собирает её модули — без этого
  // под заголовком главы мелькает «Загрузка…».
  const warm = await browser.newPage({ storageState: testInfo.project.use.storageState as string });
  await warm.goto(`${String(testInfo.project.use.baseURL)}/desk/${token}`);
  await warm.locator('.desk-project-row').first().waitFor({ timeout: 60_000 });
  await warm.close();
});

test('07-analyst-desk', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  await d.open(`/desk/${token}`, chapterTitle('Стол аналитика: кварталы и дерево задач'));

  await expect(page.locator('.desk-user-name', { hasText: ANALYST })).toBeVisible({ timeout: 60_000 });
  const projects = page.locator('.desk-project-row');
  await expect(projects.first()).toBeVisible({ timeout: 60_000 });
  await d.pause(1200);
  await page.mouse.move(900, 120);

  const switcher = page.locator('.desk-quarter-switch');
  await d.caption('Стол аналитика открывается на текущем квартале');
  await d.show(switcher);
  await d.pause(1500);

  await d.click(
    switcher.getByRole('button', { name: 'Предыдущий квартал' }),
    'Стрелки листают кварталы, выбор сохраняется в ссылке',
  );
  await expect(switcher.locator('.desk-quarter')).toHaveText(prevLabel);
  await expect(page.locator('.desk-quarter-loading')).toHaveCount(0, { timeout: 30_000 });
  await expect(page).toHaveURL(/[?&]q=\d{4}-\d/);
  const projectRow = projects.filter({ has: page.locator('.desk-project-name', { hasText: project!.title! }) });
  await expect(projectRow).toBeVisible();
  await d.show(switcher);
  await d.pause(1500);
  await page.mouse.move(900, 120);

  await d.caption('За прошлый квартал — проекты аналитика с фактом часов');
  await d.show(page.locator('.desk-tasks-summary'));
  await d.pause(2200);

  await d.click(
    projectRow.locator(':scope > button.desk-tree-btn'),
    'В «Мои проекты» задачи проекта раскрываются деревом',
  );
  const nodeRow = (key: string) =>
    page.locator('.desk-child-row', { has: page.locator('.desk-jira-key', { hasText: new RegExp(`^${key}$`) }) });
  const row1 = nodeRow(level1!.key!);
  await expect(row1).toBeVisible();
  await d.pause(1200);

  await d.click(row1.locator('button.desk-tree-btn'), 'Каждый уровень раскрывается до нижних подзадач');
  const row2 = nodeRow(level2!.key!);
  await expect(row2).toBeVisible();
  await d.click(row2.locator('button.desk-tree-btn'));
  await expect(nodeRow(kids(level2)[0].key!)).toBeVisible();
  await page.mouse.move(900, 120);
  await d.pause(1200);

  await d.caption('Справа — факт часов задачи вместе с её подзадачами');
  await d.show(row1.locator('.desk-child-hrs'));
  await d.pause(2000);
  await d.show(projectRow.locator('.desk-child-list'));
  await d.pause(3500);
  await saveClip(d, '07-analyst-desk');

  // Стол выпускался только для съёмки — отзываем.
  const res = await page.context().request.post(`${apiUrl()}/work-desks/${deskId}/revoke`);
  expect(res.ok()).toBeTruthy();
});
