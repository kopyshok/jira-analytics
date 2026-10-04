// Ролик «Как увидеть, какие команды уже взяли общую задачу»: черновик сценария
// «Команды Альфа» → жёлтая полоса «N задач уже взяли соседи» → плашка «в работе
// у K из N» у строки общей задачи → подсказка со статусами команд → «Показать
// только их» → задача включается галочкой, полоса исчезает.
// Данные подсаживаем в одноразовую копию базы (как scenario-review): общую
// задачу (RFA) делаем общей для трёх команд, эпик соседней команды «Дельта» с
// утверждённым сценарием переносим под неё, а эпик команды «Эта» помечаем
// выполненным. В afterAll всё возвращается.
import { expect, test } from '@playwright/test';
import { DatabaseSync } from 'node:sqlite';
import { fileURLToPath } from 'node:url';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
// Общая задача (RFA), под которой у Альфы есть невключённый эпик.
const RFA_KEY = 'PRH-32212';
// Эпик Альфы под ней — не включён в сценарий квартала.
const OWN_EPIC_KEY = 'PRE-123330';
// Эпик «Дельты» (включён в её утверждённый сценарий Q4) — переезжает под RFA.
const NEIGHBOR_EPIC_KEY = 'PRE-122804';
// Эпик «Эты» под той же RFA — становится выполненным.
const DONE_EPIC_KEY = 'PRE-122739';

function runDbPath(): string {
  const port = process.env.VIDEOS_BACKEND_PORT ?? '8012';
  return fileURLToPath(new URL(`../../data/demo_run_${port}.db`, import.meta.url));
}

interface ScenarioItem {
  id: string;
  year: number | null;
  quarter: string | null;
  team: string | null;
  status: 'draft' | 'approved';
}

interface IssueRow {
  id: string;
  parent_id: string | null;
  participating_teams: string | null;
  status: string;
  status_category: string | null;
}

let scenarioId = '';
let ownAllocId = '';
const saved: Partial<Record<'rfa' | 'neighbor' | 'done', IssueRow>> = {};

function issueByKey(db: DatabaseSync, key: string): IssueRow {
  const row = db
    .prepare('SELECT id, parent_id, participating_teams, status, status_category FROM issues WHERE key = ?')
    .get(key) as IssueRow | undefined;
  expect(row, `в демо-базе нет задачи ${key}`).toBeTruthy();
  return row!;
}

// Данные готовим до открытия окна — запись идёт с момента создания страницы.
test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });

  const teamsRes = await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } });
  expect(teamsRes.ok()).toBeTruthy();

  const listRes = await request.get(`${api}/planning/scenarios?teams=${encodeURIComponent(TEAM)}`);
  expect(listRes.ok()).toBeTruthy();
  const scenarios = (await listRes.json()) as ScenarioItem[];
  const scenario = scenarios.find((s) => s.team === TEAM && s.year === 2026 && s.quarter === 'Q4');
  expect(scenario, `нет сценария Q4 2026 команды ${TEAM}`).toBeTruthy();
  scenarioId = scenario!.id;
  // Полоса «взяли соседи» бывает только в черновике; в конце вернём утверждённым.
  if (scenario!.status !== 'draft') {
    const res = await request.post(`${api}/planning/scenarios/${scenarioId}/revert-to-draft`);
    expect(res.ok()).toBeTruthy();
  }

  const db = new DatabaseSync(runDbPath());
  db.exec('PRAGMA busy_timeout=5000');
  try {
    const rfa = issueByKey(db, RFA_KEY);
    const neighbor = issueByKey(db, NEIGHBOR_EPIC_KEY);
    const done = issueByKey(db, DONE_EPIC_KEY);
    saved.rfa = rfa;
    saved.neighbor = neighbor;
    saved.done = done;
    const own = db
      .prepare(
        `SELECT sa.id AS id FROM scenario_allocations sa
         JOIN backlog_items bi ON bi.id = sa.backlog_item_id
         JOIN issues i ON i.id = bi.issue_id
         WHERE sa.scenario_id = ? AND i.key = ?`,
      )
      .get(scenarioId, OWN_EPIC_KEY) as { id: string } | undefined;
    expect(own, `в сценарии нет строки ${OWN_EPIC_KEY}`).toBeTruthy();
    ownAllocId = own!.id;
    db.prepare('UPDATE scenario_allocations SET included_flag = 0 WHERE id = ?').run(ownAllocId);

    db.prepare('UPDATE issues SET participating_teams = ? WHERE id = ?').run(
      JSON.stringify([TEAM, 'Команда Дельта', 'Команда Эта']),
      rfa.id,
    );
    db.prepare('UPDATE issues SET parent_id = ? WHERE id = ?').run(rfa.id, neighbor.id);
    db.prepare("UPDATE issues SET status = 'ГОТОВО', status_category = 'done' WHERE id = ?").run(done.id);
  } finally {
    db.close();
  }

  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });

  if (saved.rfa) {
    const db = new DatabaseSync(runDbPath());
    db.exec('PRAGMA busy_timeout=5000');
    try {
      if (ownAllocId) db.prepare('UPDATE scenario_allocations SET included_flag = 0 WHERE id = ?').run(ownAllocId);
      db.prepare('UPDATE issues SET participating_teams = ? WHERE id = ?').run(
        saved.rfa.participating_teams,
        saved.rfa.id,
      );
      db.prepare('UPDATE issues SET parent_id = ? WHERE id = ?').run(saved.neighbor!.parent_id, saved.neighbor!.id);
      db.prepare('UPDATE issues SET status = ?, status_category = ? WHERE id = ?').run(
        saved.done!.status,
        saved.done!.status_category,
        saved.done!.id,
      );
    } finally {
      db.close();
    }
  }
  if (scenarioId) {
    const res = await request.get(`${api}/planning/scenarios/${scenarioId}`);
    if (res.ok()) {
      const s = (await res.json()) as { status: string };
      if (s.status !== 'approved') await request.post(`${api}/planning/scenarios/${scenarioId}/approve`);
    }
  }
  await request.dispose();
});

test('scenario-multiteam', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  await d.open(`/planning?scenario=${scenarioId}`, 'Как увидеть, какие команды уже взяли общую задачу');

  const banner = page.locator('.ant-alert', { hasText: 'уже взяли соседи' });
  await expect(banner).toBeVisible({ timeout: 20_000 });
  await d.pause(800);
  await d.poster();
  await d.pause(1200);

  const toBanner = async () => {
    await banner.evaluate((el) => el.scrollIntoView({ block: 'center', behavior: 'smooth' }));
    await d.pause(900);
  };
  await toBanner();
  await d.caption('Сценарий в черновике — над списком появилась жёлтая полоса');
  await d.show(banner);
  await d.pause(800);
  await d.caption('Эти общие задачи соседи уже взяли, а у нас они не включены');
  await d.pause(600);

  const row = page.locator(`[data-flip-wrapper][data-alloc-id="${ownAllocId}"]`);
  await expect(row).toBeVisible();
  await d.waitVoice();
  await row.evaluate((el) => el.scrollIntoView({ block: 'center', behavior: 'smooth' }));
  await d.pause(900);

  const tag = row.locator('.ant-tag', { hasText: /в работе у \d+ из \d+/ });
  await expect(tag).toBeVisible();
  await d.caption('У общей задачи — плашка: сколько команд уже взяли свою часть');
  await d.show(tag);
  await d.pause(600);

  await tag.hover();
  const tooltip = page.locator('.ant-tooltip:visible', { hasText: 'В работе у' });
  await expect(tooltip).toBeVisible({ timeout: 5_000 });
  await d.caption('В подсказке — каждая команда и что у неё с этой задачей');
  await d.show(tooltip);
  await d.pause(600);
  await d.caption('«Взят в работу» — эпик команды есть в утверждённом сценарии');
  await d.show(tooltip.getByText(/взят в работу/));
  await d.pause(600);
  await d.caption('«Выполнен» — эпик команды уже закрыт в Jira');
  await d.show(tooltip.getByText(/выполнен/));
  await d.pause(600);
  await d.caption('«Эпик есть, не взят» — команда пока не включила его в план');
  await d.show(tooltip.getByText(/эпик есть, не взят/));
  await d.waitVoice();
  await page.mouse.move(700, 120);

  await toBanner();
  await d.click(banner.getByRole('switch'), 'Включите «Показать только их» — останутся только такие задачи');
  await expect(banner.getByRole('switch')).toBeChecked();
  await page.mouse.move(700, 120);
  await d.pause(800);
  await expect(row).toBeVisible();

  await d.waitVoice();
  await row.evaluate((el) => el.scrollIntoView({ block: 'center', behavior: 'smooth' }));
  await d.pause(700);
  await d.click(row.getByRole('checkbox'), 'Нужную задачу включите в сценарий галочкой');
  await expect(row.getByRole('checkbox')).toBeChecked({ timeout: 10_000 });
  await expect(banner).toBeHidden({ timeout: 10_000 });
  await page.mouse.move(700, 120);

  await d.caption('Задача включена — полоса пропала');
  await d.show(row);
  await d.waitVoice();

  await d.click(page.locator('.side-item', { hasText: 'Целевые задачи' }), 'Та же плашка есть и в «Целевых задачах»');
  const backlogTag = page.locator('.ant-table-row .ant-tag', { hasText: /в работе у \d+ из \d+/ }).first();
  await expect(backlogTag).toBeVisible({ timeout: 20_000 });
  await d.pause(600);
  await d.caption('Там она стоит рядом с эпиками общих задач');
  await d.show(backlogTag);
  await d.pause(800);

  await d.caption('Готово', 2200);
  await d.save('scenario-multiteam');
});
