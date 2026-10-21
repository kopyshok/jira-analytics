// Глава «Карточка задачи в панели и ворклоги сотрудника»: Аналитика в «Пульте»,
// дерево «сотрудник → задача» → щелчок по задаче → карточка в панели снизу →
// в ворклогах только сотрудник строки («Только … · N из M») → переключатель —
// ворклоги всех → панель справа → на весь экран → Esc.
// Задача — та, где списывали несколько человек, и стоит у сотрудника в первых строках.
import { expect, test } from '@playwright/test';
import { Director } from '../director.ts';
import { chapterTitle, releaseFrame, saveClip } from './common.ts';

const TEAM = 'Команда Альфа';
const YEAR = 2026;
const QUARTER = 3;

type Issue = { id: string; key: string; totals: { fact_hours: number; worklog_count: number } };
type Report = {
  teams: {
    roles: {
      employees: {
        employee_id: string;
        name: string;
        work_types: { categories: { issues: Issue[] }[] }[];
      }[];
    }[];
  }[];
};

releaseFrame();

let heroName = '';
let issueKey = '';
let mine = 0;

test.beforeAll(async ({ playwright }, testInfo) => {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({
    storageState: testInfo.project.use.storageState as string,
  });
  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  expect((await request.put(`${api}/users/me/period`, { data: { year: YEAR, quarter: QUARTER } })).ok()).toBeTruthy();
  expect((await request.put(`${api}/users/me/theme`, { data: { theme: 'pult-light' } })).ok()).toBeTruthy();
  // Дерево «сотрудник → задача»: остальные уровни скрыты, чтобы до задачи был один щелчок.
  expect(
    (
      await request.put(`${api}/users/me/analytics-layout`, {
        data: {
          layout: {
            group_order: ['team', 'subgroup', 'role', 'employee', 'work_type', 'category', 'issue'],
            hidden_levels: ['subgroup', 'role', 'work_type', 'category'],
            active_preset: 'default',
            show_fact_bar: true,
          },
        },
      })
    ).ok(),
  ).toBeTruthy();

  const res = await request.get(`${api}/analytics/report`, { params: { year: YEAR, quarter: QUARTER, teams: TEAM } });
  expect(res.ok()).toBeTruthy();
  const report = (await res.json()) as Report;

  // Задачи каждого сотрудника по убыванию факта — как строки дерева.
  const people = report.teams.flatMap((t) => t.roles.flatMap((r) => r.employees)).map((e) => ({
    id: e.employee_id,
    name: e.name,
    issues: e.work_types
      .flatMap((w) => w.categories.flatMap((c) => c.issues))
      .sort((a, b) => b.totals.fact_hours - a.totals.fact_hours),
  }));
  const writers = new Map<string, number>();
  for (const p of people) for (const i of p.issues) writers.set(i.id, (writers.get(i.id) ?? 0) + 1);
  // Сотрудник с задачей в первых строках, где списывали ещё хотя бы трое,
  // а своих ворклогов немного — разница со «всеми» видна сразу.
  const candidates = people
    .flatMap((p) => p.issues.slice(0, 8).map((i, rank) => ({ p, i, rank, n: writers.get(i.id) ?? 0 })))
    .filter((x) => x.n >= 4 && x.i.totals.worklog_count >= 2 && x.i.totals.worklog_count <= 30)
    .sort((a, b) => a.rank - b.rank || b.n - a.n);
  // Число ворклогов в строке отчёта и в карточке должно совпасть: у сотрудника, бывшего
  // в команде не весь квартал, отчёт режет часы по датам участия, а карточка — нет.
  let pick: (typeof candidates)[number] | undefined;
  for (const c of candidates) {
    const wl = await request.get(`${api}/analytics/report/issue/${c.i.id}/worklogs`, {
      params: { start: `${YEAR}-07-01`, end: `${YEAR}-09-30` },
    });
    expect(wl.ok()).toBeTruthy();
    const list = (await wl.json()) as { employee_id: string }[];
    if (list.filter((w) => w.employee_id === c.p.id).length === c.i.totals.worklog_count) {
      pick = c;
      break;
    }
  }
  await request.dispose();
  expect(pick, 'нет задачи, где списывали несколько человек').toBeTruthy();
  heroName = pick!.p.name;
  issueKey = pick!.i.key;
  mine = pick!.i.totals.worklog_count;
});

test('02-issue-panel', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  await page.addInitScript(() => localStorage.setItem('app_theme', 'pult-light'));
  await d.open('/analytics', chapterTitle('Карточка задачи в панели и ворклоги сотрудника'));

  const row = (text: string) => page.locator('tr.ant-table-row', { hasText: text }).first();
  await expect(row(heroName)).toBeVisible({ timeout: 60_000 });
  // Ворклоги — в карточке, а не строкой под задачей.
  const drawerMode = page.locator('.ant-segmented-item', { hasText: 'drawer' });
  if (!(await drawerMode.getAttribute('class'))?.includes('selected')) await drawerMode.click();
  await page.mouse.move(1100, 600);
  await d.pause(1500);

  await d.click(row(heroName), 'Аналитика: часы команды по сотрудникам и задачам');
  const issueRow = page.locator('tr.ant-table-row', { has: page.getByText(issueKey, { exact: true }) }).first();
  await expect(issueRow).toBeVisible();
  await d.pause(1000);

  await d.click(issueRow.locator('td').nth(2), 'Щелчок по задаче — карточка открывается в панели снизу');
  const sheet = page.locator('.detail-sheet');
  await expect(sheet).toBeVisible();
  const only = sheet.locator('label', { hasText: 'Только' });
  await expect(only).toContainText(`${mine} из`, { timeout: 30_000 });
  await page.mouse.move(1100, 300);
  await d.pause(1200);

  await d.caption('В ворклогах — только сотрудник, из чьей строки открыта задача');
  await d.show(only);
  await d.pause(2500);
  await d.show(sheet.locator('.ant-table').last());
  await d.pause(2000);
  await d.waitVoice();

  await d.click(only.getByRole('switch'), 'Переключатель возвращает ворклоги всех. Фильтр работает во всех темах');
  await d.show(sheet.locator('.ant-table').last());
  await d.pause(3000);
  await d.waitVoice();

  await d.click(
    sheet.getByRole('button', { name: 'Показать панелью справа' }),
    'Панель можно поставить справа…',
  );
  await expect(page.locator('.detail-sheet--right')).toBeVisible();
  await page.mouse.move(700, 500);
  await d.pause(2500);

  await d.click(sheet.getByRole('button', { name: 'Развернуть на весь экран' }), '…или развернуть на весь экран');
  await page.mouse.move(900, 600);
  await d.pause(2500);
  await d.click(sheet.getByRole('button', { name: 'Свернуть' }));
  await d.waitVoice();

  await d.caption('Место и размер панели запоминаются, Esc — закрыть');
  await d.pause(2500);
  await page.keyboard.press('Escape');
  await expect(sheet).toHaveCount(0);
  await d.pause(2000);
  await saveClip(d, '02-issue-panel');
});
