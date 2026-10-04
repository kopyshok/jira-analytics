// Ролик «Как увидеть минорные изменения и кто взял общую задачу»: Целевые задачи →
// переключатель «Минорные изменения» → карточки по командам (открыто, с оценкой,
// без оценки, запас на квартал, список задач) → у мультикомандной RFA метка
// «мультикоманда» и плашка «в работе у K из N» с подсказкой по командам.
// Данные: минорные задачи и мультикомандные RFA в демо-базе уже есть; у двух
// минорных задач Альфы временно проставляем оценки (в afterAll возвращаем).
import { expect, test } from '@playwright/test';
import { DatabaseSync } from 'node:sqlite';
import { fileURLToPath } from 'node:url';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
const TEAMS = [TEAM, 'Команда Лямбда'];

interface MinorTask { key: string; hours: Record<string, number | null> }
interface MinorBlock { team: string; tasks: MinorTask[] }
interface Progress { taken: number; total: number; own_status: string }
interface BacklogRow { id: string; jira_key: string | null; is_multi_team: boolean; multi_team_progress: Progress | null }

function runDbPath(): string {
  const port = process.env.VIDEOS_BACKEND_PORT ?? '8012';
  return fileURLToPath(new URL(`../../data/demo_run_${port}.db`, import.meta.url));
}

const ROLE_COLS = ['planned_analyst_hours_manual', 'planned_dev_hours_manual', 'planned_qa_hours_manual', 'planned_opo_hours_manual'];
const SEEDED: Record<string, (number | null)[]> = {};
let rfaId = '';

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  // Сначала смотрим на одну команду: оценки подсаживаем только её задачам.
  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  const summary = await (await request.get(`${api}/backlog/minor-changes-summary`, { params: { teams: TEAM } })).json();
  const block = (summary.teams as MinorBlock[]).find((t) => t.team === TEAM);
  expect(block, `У команды ${TEAM} нет открытых минорных задач`).toBeTruthy();
  const bare = block!.tasks.filter((t) => Object.values(t.hours).every((v) => !v));
  if (bare.length >= 2) {
    const db = new DatabaseSync(runDbPath());
    db.exec('PRAGMA busy_timeout=5000');
    try {
      const plan: (number | null)[][] = [[8, 24, 8, null], [null, 16, 4, null]];
      bare.slice(0, 2).forEach((t, i) => {
        const old = db.prepare(`SELECT ${ROLE_COLS.join(',')} FROM issues WHERE key = ?`).get(t.key) as Record<string, number | null>;
        SEEDED[t.key] = ROLE_COLS.map((c) => old[c] ?? null);
        db.prepare(`UPDATE issues SET ${ROLE_COLS.map((c) => `${c} = ?`).join(', ')} WHERE key = ?`).run(...plan[i], t.key);
      });
    } finally {
      db.close();
    }
  }

  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: TEAMS, subgroups: [] } })).ok()).toBeTruthy();
  const rows: BacklogRow[] = await (await request.get(`${api}/backlog`, { params: { view: 'active', teams: TEAMS.join(',') } })).json();
  const rfa = rows.find((r) => r.is_multi_team && r.multi_team_progress
    && r.multi_team_progress.taken > 0 && r.multi_team_progress.taken < r.multi_team_progress.total);
  expect(rfa, 'На вкладке «Бэклог» нет мультикомандной RFA с частично взятой работой').toBeTruthy();
  rfaId = rfa!.id;
  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  if (Object.keys(SEEDED).length) {
    const db = new DatabaseSync(runDbPath());
    db.exec('PRAGMA busy_timeout=5000');
    try {
      for (const [key, old] of Object.entries(SEEDED)) {
        db.prepare(`UPDATE issues SET ${ROLE_COLS.map((c) => `${c} = ?`).join(', ')} WHERE key = ?`).run(...old, key);
      }
    } finally {
      db.close();
    }
  }
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } });
  await request.dispose();
});

test('backlog-minor-multiteam', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  await d.open('/backlog?view=active', 'Как увидеть минорные изменения и кто взял общую задачу');
  const pane = page.locator('[data-tour="backlog-tabs"] .ant-tabs-tabpane-active');
  await expect(pane.locator('tbody tr.ant-table-row').first()).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  const toggle = page.getByRole('checkbox', { name: 'Минорные изменения' });
  await d.click(toggle, 'Включите переключатель «Минорные изменения»');
  const cards = page.locator('.ant-card', { has: page.locator('.ant-statistic') });
  await expect(cards.first()).toBeVisible({ timeout: 20_000 });
  await expect(cards).toHaveCount(2);
  await page.mouse.move(700, 120);

  const card = cards.first();
  await d.caption('Над таблицей — карточка по каждой команде');
  await d.show(card);
  await d.pause(600);
  const stat = (title: string) => card.locator('.ant-statistic', { hasText: title }).first();
  await d.caption('«Открыто» — сколько минорных задач ещё в работе');
  await d.show(stat('Открыто'));
  await d.pause(600);
  await d.caption('«С оценкой» — число задач и часы по ролям');
  await d.show(stat('С оценкой'));
  await d.pause(600);
  await d.caption('«Без оценки» — только штуки, часы не придумываются');
  await d.show(stat('Без оценки'));
  await d.pause(600);
  await d.caption('«Заложено на квартал» — запас из правил команды');
  await d.show(stat('Заложено на квартал'));
  await d.pause(600);

  await d.click(card.getByText(/Список задач/), 'Раскройте «Список задач»');
  const list = card.locator('.ant-table').first();
  await expect(list).toBeVisible();
  await d.show(list);
  await d.pause(600);
  await d.caption('Какие задачи минорные, решает категория из раздела «Категории задач»');
  await d.pause(500);

  await d.waitVoice();
  await d.click(toggle, 'Выключите переключатель — таблица снова на месте');
  await expect(card).toBeHidden();
  await page.mouse.move(700, 120);

  const row = pane.locator(`tr[data-row-key="${rfaId}"]`);
  await expect(row).toBeVisible({ timeout: 15_000 });
  await row.scrollIntoViewIfNeeded();
  const multiTag = row.locator('.ant-tag', { hasText: 'мультикоманда' }).first();
  await d.caption('Над такой задачей работают сразу несколько команд');
  await d.show(multiTag);
  await d.pause(600);

  const plate = row.locator('.ant-tag', { hasText: /в работе у/ }).first();
  await d.caption('Плашка показывает, сколько команд уже взяли задачу в работу');
  await d.point(plate);
  await plate.hover();
  const tip = page.locator('.ant-tooltip:visible', { hasText: 'команд' });
  await expect(tip).toBeVisible();
  await d.pause(800);
  await d.caption('В подсказке — каждая команда и её статус');
  await d.show(tip);
  await d.pause(800);
  await d.caption('В «Сценариях» эта плашка предупреждает о соседних командах');
  await d.pause(600);
  await d.waitVoice();

  await d.caption('Готово', 2200);
  await d.save('backlog-minor-multiteam');
});
