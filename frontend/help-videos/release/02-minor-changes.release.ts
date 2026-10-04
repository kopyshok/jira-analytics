// Глава «Сводка минорных изменений»: «Целевые задачи» → переключатель «Минорные
// изменения» → карточка по каждой команде шапки: открыто, без оценки, заложено на
// квартал, с оценкой и часами по ролям → раскрыть список задач команды.
// В демо-базе у открытых минорных задач нет оценок. Чтобы показать часы по ролям,
// глава относит к «Минорным изменениям» эпик команды Кси с оценённой задачей — так же,
// как это делает пользователь в «Категориях задач», — и после съёмки возвращает как было.
import { expect, test } from '@playwright/test';
import { Director } from '../director.ts';
import { chapterTitle, releaseFrame, saveClip } from './common.ts';

/** Основная команда: много открытых минорных задач и запас на квартал. */
const TEAM = 'Команда Альфа';
/** Вторая команда: после правки категории — одна задача с оценками по ролям. */
const ESTIMATED_TEAM = 'Команда Кси';
/** Эпик команды Кси, под которым единственная в демо-базе открытая задача с оценкой. */
const EPIC_KEY = 'PRH-32503';
const MINOR = 'minor_change';

type Me = { selected_teams: string[]; selected_subgroups: string[] };
type Located = { found: boolean; id: string | null; ancestor_ids: string[] };
type TreeNode = {
  id: string;
  key: string;
  assigned_category: string | null;
  parent_changed: boolean;
  category_context: string | null;
  category_context_key: string | null;
};
type MinorTeam = { team: string; open_count: number; estimated_count: number; unestimated_count: number; reserve_hours: number | null };

releaseFrame();

let teamsBefore: Me | null = null;
let epicId = '';
let parentId = '';
/** Категория эпика и пометки разбора до главы — вернуть после. */
let epicBefore: TreeNode | null = null;

const sameMarks = (a: TreeNode, b: TreeNode) =>
  a.assigned_category === b.assigned_category &&
  a.parent_changed === b.parent_changed &&
  a.category_context === b.category_context &&
  a.category_context_key === b.category_context_key;

// Данные готовим до открытия окна: иначе в начале ролика — тёмные секунды.
test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  const getJson = async <T,>(url: string, params?: Record<string, string>): Promise<T> => {
    const res = await request.get(url, { params });
    expect(res.ok(), url).toBeTruthy();
    return (await res.json()) as T;
  };

  teamsBefore = await getJson<Me>(`${api}/auth/me`);
  const put = await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM, ESTIMATED_TEAM], subgroups: [] } });
  expect(put.ok()).toBeTruthy();

  const located = await getJson<Located>(`${api}/issues/locate`, { key: EPIC_KEY });
  expect(located.found && located.ancestor_ids.length, `нет эпика ${EPIC_KEY} с родителем`).toBeTruthy();
  epicId = located.id!;
  parentId = located.ancestor_ids[located.ancestor_ids.length - 1];
  const siblings = await getJson<TreeNode[]>(`${api}/issues/${parentId}/children`);
  epicBefore = siblings.find((n) => n.id === epicId) ?? null;
  expect(epicBefore, `эпик ${EPIC_KEY} не найден среди детей родителя`).toBeTruthy();

  if (epicBefore!.assigned_category !== MINOR) {
    const set = await request.put(`${api}/issues/${epicId}/category`, { data: { category_code: MINOR } });
    expect(set.ok(), await set.text()).toBeTruthy();
  }

  // Сводка должна показать обе стороны: задачи без оценки с запасом и задачу с часами.
  const summary = await getJson<{ teams: MinorTeam[] }>(`${api}/backlog/minor-changes-summary`, {
    teams: `${TEAM},${ESTIMATED_TEAM}`,
  });
  const main = summary.teams.find((t) => t.team === TEAM);
  const estimated = summary.teams.find((t) => t.team === ESTIMATED_TEAM);
  expect(main?.unestimated_count, `у ${TEAM} нет минорных задач без оценки`).toBeGreaterThan(0);
  expect(main?.reserve_hours, `у ${TEAM} нет запаса на минорные изменения`).toBeTruthy();
  expect(estimated?.estimated_count, `у ${ESTIMATED_TEAM} нет оценённой минорной задачи`).toBeGreaterThan(0);
  await request.dispose();
});

// Категорию эпика и команды шапки возвращаем — даже если съёмка упала.
test.afterAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  if (epicBefore && epicBefore.assigned_category !== MINOR) {
    const res = await request.put(`${api}/issues/${epicId}/category`, {
      data: { category_code: epicBefore.assigned_category },
    });
    expect(res.ok()).toBeTruthy();
    // Возврат категории пересчитывает и пометки разбора — они должны совпасть с исходными.
    const after = ((await (await request.get(`${api}/issues/${parentId}/children`)).json()) as TreeNode[]).find(
      (n) => n.id === epicId,
    );
    expect(after && sameMarks(after, epicBefore), 'эпик не вернулся в исходное состояние').toBeTruthy();
  }
  if (teamsBefore) {
    const res = await request.put(`${api}/auth/me/teams`, {
      data: { teams: teamsBefore.selected_teams, subgroups: teamsBefore.selected_subgroups },
    });
    expect(res.ok()).toBeTruthy();
  }
  await request.dispose();
});

test('02-minor-changes', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  await d.open('/backlog', chapterTitle('Сводка минорных изменений'));

  const pane = page.locator('[data-tour="backlog-tabs"] .ant-tabs-tabpane-active');
  await expect(pane.locator('tbody tr.ant-table-row').first()).toBeVisible({ timeout: 60_000 });
  await d.pause(1800);

  const toggle = page.getByRole('checkbox', { name: 'Минорные изменения' });
  await d.click(toggle, 'На «Целевых задачах» включите «Минорные изменения»');
  await expect(toggle).toHaveAttribute('aria-checked', 'true');

  const card = (team: string) =>
    page.locator('.ant-card', { has: page.locator('.ant-card-head-title', { hasText: new RegExp(`^${team}$`) }) });
  const main = card(TEAM);
  const other = card(ESTIMATED_TEAM);
  const stat = (c: typeof main, title: string) => c.locator('.ant-statistic', { hasText: title });
  await expect(stat(main, 'Открыто')).toBeVisible({ timeout: 30_000 });
  await expect(stat(other, 'С оценкой')).toBeVisible();
  await page.mouse.move(960, 60);
  await d.pause(900);

  await d.caption('По каждой команде — сколько минорных задач открыто');
  await d.show(main);
  await d.pause(900);
  await d.show(stat(main, 'Открыто'));
  await d.pause(2200);

  await d.caption('Сколько из них без оценки и сколько заложено на квартал');
  await d.show(stat(main, 'Без оценки'), stat(main, 'Заложено на квартал'));
  await d.pause(3000);

  // Под значением «С оценкой» — строка часов по ролям: показываем их вместе.
  await d.caption('Оценённые задачи — с часами по ролям из оценок Jira');
  await d.show(stat(other, 'С оценкой').locator('xpath=..'));
  await d.pause(3200);

  const listHeader = main.locator('.ant-collapse-header');
  await d.click(listHeader, 'Список задач команды раскрывается');
  const table = main.locator('.ant-table');
  const rows = table.locator('.ant-table-row');
  await expect(rows.first()).toBeVisible();
  await page.mouse.move(960, 60);
  // Карточка команды — к верху экрана, плавно: название команды и список в кадре.
  await main.evaluate((el) => el.scrollIntoView({ block: 'start', behavior: 'smooth' }));
  await d.pause(900);
  // Последняя строка, целиком видимая над подписью внизу экрана.
  let last = 0;
  for (let i = 0, n = await rows.count(); i < n; i++) {
    const box = await rows.nth(i).boundingBox();
    if (!box || box.y + box.height > 960) break;
    last = i;
  }
  await d.show(table.locator('thead'), rows.nth(last));
  await d.pause(2800);

  // Колонка «Эпик» — последняя: эпик задачи виден, но сам в счёт не идёт.
  await d.caption('Эпик указан для справки, эпики-контейнеры в счёт не идут');
  await d.show(rows.first().locator('td').last(), rows.nth(last).locator('td').last());
  await d.pause(4200);
  await saveClip(d, '02-minor-changes');
});
