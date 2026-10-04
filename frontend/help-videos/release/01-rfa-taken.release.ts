// Глава «RFA нескольких команд: кто уже взял работу»: «Целевые задачи» команды →
// плашка «в работе у K из N» у эпика мультикомандной RFA → подсказка со статусом
// каждой команды (взят — со сценарием, выполнен, не взят, нет эпика) → черновик
// сценария своей команды → предупреждение «… уже взяли соседи, у вас не включены» →
// «Показать только их».
// «Взят» — эпик команды в утверждённом сценарии текущего или будущего квартала, а
// предупреждение бывает только в черновике. У команды Эта в демо-базе квартал
// утверждён, поэтому глава заводит черновик следующего квартала и после удаляет его.
import { expect, type APIRequestContext, type Locator, type Page, test } from '@playwright/test';
import { Director } from '../director.ts';
import { chapterTitle, releaseFrame, saveClip } from './common.ts';

/** Команда, у эпиков которой в демо-базе работу по RFA взяли и соседи, и она сама. */
const TEAM = 'Команда Эта';

type TakeStatus = 'taken' | 'done' | 'not_taken' | 'no_epic';
type Progress = {
  taken: number;
  total: number;
  own_team: string | null;
  teams: { team: string; status: TakeStatus }[];
};
type BacklogRow = { id: string; jira_status_category?: string | null; multi_team_progress?: Progress | null };
type Alloc = { id: string; included: boolean; multi_team_progress?: Progress | null };
type Scenario = { id: string; name: string; team: string | null; year: number | null; quarter: string | null };
type Me = { selected_teams: string[]; selected_subgroups: string[] };

releaseFrame();

let rowId = '';
let scenarioId = '';
let scenarioName = '';
/** Сколько строк черновика попадёт под предупреждение о соседях. */
let neighborRows = 0;
/** Команды шапки до главы — вернуть после. */
let teamsBefore: Me | null = null;

/** Первый квартал, на который у команды ещё нет сценария (не раньше следующего за текущим). */
async function nextFreeQuarter(request: APIRequestContext, api: string): Promise<{ year: number; quarter: number }> {
  const res = await request.get(`${api}/planning/scenarios`, { params: { teams: TEAM } });
  expect(res.ok()).toBeTruthy();
  const keys = ((await res.json()) as Scenario[])
    .filter((s) => s.team === TEAM && s.year != null && s.quarter != null)
    .map((s) => (s.year as number) * 4 + (Number((s.quarter as string).replace('Q', '')) - 1));
  const now = new Date();
  const nextKey = Math.max(now.getFullYear() * 4 + Math.floor(now.getMonth() / 3), ...keys) + 1;
  return { year: Math.floor(nextKey / 4), quarter: (nextKey % 4) + 1 };
}

/** Обвести область карточки по её ширине — от верха `from` до низа `to`: строки
 *  сценария шире видимой части карточки (прокрутка вбок), рамка по строке ушла бы за край. */
async function ringRows(page: Page, card: Locator, from: Locator, to: Locator): Promise<void> {
  const c = await card.boundingBox();
  const a = await from.boundingBox();
  const b = await to.boundingBox();
  if (!c || !a || !b) throw new Error('Строки сценария не видны на экране');
  // Низ рамки — не ниже подписи внизу кадра.
  const bottom = Math.min(b.y + b.height, page.viewportSize()!.height - 130);
  const rect = { x: c.x + 8, y: a.y, width: c.width - 16, height: bottom - a.y };
  await page.evaluate((r) => {
    window.__director?.ring(r);
    window.__director?.move(r.x + r.width - 10, r.y + r.height + 16);
  }, rect);
  await page.waitForTimeout(750);
}

/** Строку сценария соседи по RFA уже взяли (или выполнили), а здесь она не включена. */
function takenByNeighbors(a: Alloc): boolean {
  const p = a.multi_team_progress;
  return (
    !a.included &&
    !!p &&
    p.teams.some((t) => (t.status === 'taken' || t.status === 'done') && t.team !== p.own_team)
  );
}

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
  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();

  // Строка «Активных» с плашкой, в подсказке которой есть все статусы:
  // соседи взяли и выполнили, у кого-то эпик не взят или его нет. Сама задача —
  // не закрытая: иначе «Готово» в строке спорит с «взят в работу» в подсказке.
  const rows = await getJson<BacklogRow[]>(`${api}/backlog`, { view: 'quarterly', teams: TEAM });
  const allStatuses = (r: BacklogRow) => {
    const s = new Set(r.multi_team_progress?.teams.map((t) => t.status) ?? []);
    return s.has('taken') && s.has('done') && (s.has('not_taken') || s.has('no_epic'));
  };
  const row =
    rows.find((r) => allStatuses(r) && r.jira_status_category !== 'done') ?? rows.find(allStatuses);
  expect(row, `у команды ${TEAM} нет мультикомандной RFA со всеми статусами`).toBeTruthy();
  rowId = row!.id;

  // Черновик следующего свободного квартала: в него попадают кандидаты команды.
  const { year, quarter } = await nextFreeQuarter(request, api);
  scenarioName = `${year} Q${quarter} ${TEAM}`;
  const created = await request.post(`${api}/planning/scenarios`, {
    data: { name: scenarioName, year, quarter, team: TEAM },
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  scenarioId = ((await created.json()) as { id: string }).id;

  // Отбор «Показать только их» должен что-то убрать: нужны и такие строки, и другие.
  const allocs = await getJson<Alloc[]>(`${api}/planning/scenarios/${scenarioId}/allocations`);
  neighborRows = allocs.filter(takenByNeighbors).length;
  expect(neighborRows, 'в черновике нет задач, взятых соседями').toBeGreaterThan(0);
  expect(allocs.length, 'в черновике только задачи соседей — отбору нечего убрать').toBeGreaterThan(neighborRows);
  await request.dispose();
});

// Черновик удаляем, команды шапки возвращаем — даже если съёмка упала.
test.afterAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  if (scenarioId) expect((await request.delete(`${api}/planning/scenarios/${scenarioId}`)).ok()).toBeTruthy();
  if (teamsBefore) {
    const res = await request.put(`${api}/auth/me/teams`, {
      data: { teams: teamsBefore.selected_teams, subgroups: teamsBefore.selected_subgroups },
    });
    expect(res.ok()).toBeTruthy();
  }
  await request.dispose();
});

test('01-rfa-taken', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  await d.open('/backlog', chapterTitle('RFA нескольких команд: кто уже взял работу'));

  const pane = page.locator('[data-tour="backlog-tabs"] .ant-tabs-tabpane-active');
  const row = pane.locator(`tr[data-row-key="${rowId}"]`);
  await expect(row).toBeVisible({ timeout: 60_000 });
  const tag = row.locator('.ant-tag', { hasText: /^в работе у \d+ из \d+$/ });
  await expect(tag).toBeVisible();
  // Строка — к середине экрана, плавно (ещё под заголовком главы).
  await row.evaluate((el) => el.scrollIntoView({ block: 'center', behavior: 'smooth' }));
  await d.pause(1300);

  await d.caption('Плашка у RFA нескольких команд — сколько команд уже взяли работу');
  await d.show(tag);
  await d.pause(2000);

  await d.caption('В подсказке — статус каждой команды и её сценарий');
  await d.point(tag);
  await tag.hover();
  const tip = page.locator('.ant-tooltip:visible', { hasText: 'В работе у' });
  await expect(tip).toBeVisible();
  await d.pause(300);
  await d.show(tip);
  await d.pause(3000);

  // Строки подсказки — самые глубокие div без вложенных.
  // Строка с кварталом последнего плана, если такая есть, — она подробнее.
  const lines = tip.locator('div:not(:has(div))');
  const withQuarter = lines.filter({ hasText: /— выполнен \(/ });
  const doneLine = (await withQuarter.count()) ? withQuarter.first() : lines.filter({ hasText: '— выполнен' }).first();
  await d.caption('Эпик, закрытый в Jira, считается взятым — «выполнен»');
  await d.show(doneLine);
  await d.pause(2600);
  await page.evaluate(() => window.__director?.ring(null));
  await page.mouse.move(960, 60);

  await d.click(page.locator('.side-item', { hasText: 'Сценарии' }), 'Откройте черновик сценария своей команды');
  const select = page.locator('[data-tour="planning-scenario-select"]');
  await expect(select).toBeVisible({ timeout: 30_000 });
  // Без запомненного выбора страница сама берёт самый поздний квартал — черновик главы.
  if (!(await select.innerText()).includes(scenarioName)) {
    await d.click(select);
    await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: scenarioName }));
  }
  await expect(select).toContainText(scenarioName);

  const banner = page.locator('.ant-alert', { hasText: 'уже взяли соседи' });
  await expect(banner).toBeVisible({ timeout: 30_000 });
  const rows = page.locator('[data-flip-wrapper]');
  await expect(rows.first()).toBeVisible();
  const allRows = await rows.count();
  // Прокрутку оставляем на после отбора: страница ещё дособирается, и ранняя
  // прокрутка отскакивает обратно. Предупреждение видно и так.
  const card = page.locator('.ant-card', { has: page.locator('.ant-card-head', { hasText: 'Элементы бэклога' }) });
  await d.pause(900);

  await d.caption('Предупреждение: эти задачи уже взяли соседи, у вас не включены');
  await d.show(banner);
  await d.pause(2600);

  await d.click(banner.getByRole('switch'), '«Показать только их» оставляет в списке только такие задачи');
  await expect(rows).toHaveCount(neighborRows);
  expect(allRows).toBeGreaterThan(neighborRows);
  await page.mouse.move(960, 60);
  // Предупреждение — к верху экрана: под ним все оставшиеся строки.
  await banner.evaluate((el) => el.scrollIntoView({ block: 'start', behavior: 'smooth' }));
  await d.pause(900);
  await ringRows(page, card, rows.first(), rows.last());
  await d.pause(3600);
  await saveClip(d, '01-rfa-taken');
});
