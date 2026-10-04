// Ролик «Как пользоваться личным рабочим столом»: Ресурсы → «Рабочие столы» (стол уже выпущен,
// ссылка у аналитика) → стол по ссылке: шапка → переключатель квартала → «Мои проекты»
// с деревом задач до нижних подзадач → таймлайн и занятость команды → переключатель темы.
//
// Подготовка (beforeAll): берётся существующий стол сотрудника или выпускается новый;
// выпущенный нами отзывается в afterAll.
import { type APIRequestContext, expect, test } from '@playwright/test';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
const ANALYST = 'Ильина Марина';

let ctx: APIRequestContext;
let api = '';
let token = '';
let createdDeskId: string | null = null;

type DeskItem = { id: string; token: string | null; employee: { id: string; display_name: string } };

test.beforeAll(async ({ playwright }) => {
  const info = test.info();
  api = `${String(info.config.metadata.backendUrl)}/api/v1`;
  ctx = await playwright.request.newContext({ storageState: info.project.use.storageState as string });
  expect((await ctx.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();

  const employees: { id: string; display_name: string }[] = await (await ctx.get(`${api}/employees`)).json();
  const emp = employees.find((e) => e.display_name === ANALYST);
  if (!emp) throw new Error(`В демо-базе нет сотрудника ${ANALYST}`);

  const desks: DeskItem[] = await (await ctx.get(`${api}/work-desks`)).json();
  const existing = desks.find((x) => x.employee.id === emp.id && x.token);
  if (existing?.token) {
    token = existing.token;
  } else {
    const res = await ctx.post(`${api}/work-desks`, {
      data: {
        employee_id: emp.id,
        enabled_widgets: [
          'my_tasks', 'my_timeline', 'stale_tasks', 'hours_balance', 'category_breakdown',
          'team_absences', 'team_availability', 'production_calendar', 'awaiting_reaction',
        ],
      },
    });
    expect(res.ok()).toBeTruthy();
    const created: { id: string; token: string } = await res.json();
    token = created.token;
    createdDeskId = created.id;
  }
});

test.afterAll(async () => {
  if (createdDeskId) await ctx.post(`${api}/work-desks/${createdDeskId}/revoke`, { data: {} });
  await ctx.dispose();
});

test('desk-analyst-use', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  await d.open('/capacity', 'Как пользоваться личным рабочим столом');
  await expect(page.locator('[data-tour="capacity-team-table"] tbody tr.capacity-emp-row').first()).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1100);

  await d.click(page.locator('.side-item', { hasText: 'Ресурсы' }), 'Откройте раздел «Ресурсы»');
  await d.click(page.getByRole('tab', { name: 'Рабочие столы' }), 'Вкладка «Рабочие столы»');
  const deskRow = page.locator('.ant-tabs-tabpane-active tr', { hasText: ANALYST });
  await expect(deskRow.locator('.ant-tag', { hasText: 'Активен' })).toBeVisible();
  await d.caption('Стол аналитика уже выпущен — ссылку он получил от вас');
  await d.show(deskRow);
  await d.waitVoice();

  // Дальше — глазами аналитика: страница по ссылке, вход в сервис не нужен.
  await page.goto(`/desk/${token}`);
  await expect(page.locator('.desk-user-name', { hasText: ANALYST })).toBeVisible({ timeout: 15_000 });
  await expect(page.locator('.desk-zone').first()).toBeVisible();
  await page.mouse.move(1436, 450);
  await d.caption('Вверху — переработка, рабочие дни до конца месяца и проекты в работе');
  await d.show(page.locator('.desk-header'));
  await d.waitVoice();

  // Квартал: стрелки переключают все виджеты сразу.
  const prev = page.getByRole('button', { name: 'Предыдущий квартал' });
  const next = page.getByRole('button', { name: 'Следующий квартал' });
  const loading = page.locator('.desk-quarter-loading');
  await d.click(prev, 'Стрелки переключают квартал сразу у всех виджетов');
  await expect(loading).toBeHidden({ timeout: 20_000 });
  await d.pause(900);
  await d.waitVoice();
  await d.click(next);
  await expect(loading).toBeHidden({ timeout: 20_000 });
  await page.mouse.move(1436, 450);

  // «Мои проекты».
  const projects = page.locator('.desk-zone', { hasText: 'Мои проекты' }).first();
  await projects.scrollIntoViewIfNeeded();
  await d.caption('Проекты и приоритеты стол берёт из утверждённых сценариев');
  await d.show(projects.locator('.desk-tasks-summary'));
  await d.waitVoice();

  const rowWithKids = projects.locator('.desk-project-row', { has: page.locator('.desk-child-toggle') }).first();
  await expect(rowWithKids).toBeVisible();
  await d.click(rowWithKids.locator('.desk-child-toggle'), 'Кнопка «подзадачи» раскрывает задачи проекта');
  const treeRows = rowWithKids.locator('[data-testid="desk-tree-row"]');
  await expect(treeRows.first()).toBeVisible();
  await page.mouse.move(1436, 450);
  await d.show(rowWithKids.locator('.desk-child-list'));
  await d.waitVoice();

  // Глубже — стрелкой у каждой задачи, пока не дойдём до нижнего уровня.
  await d.caption('Каждый уровень раскрывается своей стрелкой — до нижних подзадач');
  for (let level = 0; level < 4; level++) {
    const arrow = rowWithKids.locator('.desk-child-row .desk-tree-chevron:not(.hidden):not(.open)').first();
    if (!(await arrow.count())) break;
    await d.click(arrow);
  }
  await page.mouse.move(1436, 450);
  await d.show(rowWithKids.locator('.desk-child-list'));
  await d.waitVoice();
  await d.caption('В дереве только списанные часы, закрытые задачи приглушены');
  await d.show(treeRows.first(), treeRows.last());
  await d.waitVoice();

  // Таймлайн и занятость команды.
  const timeline = page.locator('.desk-zone', { hasText: 'Таймлайн моих проектов' }).first();
  await timeline.scrollIntoViewIfNeeded();
  await d.caption('Таймлайн — фазы проектов на шкале квартала');
  await d.show(timeline);
  await d.waitVoice();

  const availability = page.locator('.desk-zone', { hasText: 'Занятость команды' }).first();
  await availability.scrollIntoViewIfNeeded();
  await d.caption('Занятость команды — на каких проектах заняты коллеги');
  await d.show(availability);
  await d.waitVoice();

  const absences = page.locator('.desk-zone', { hasText: 'Отсутствия команды' }).first();
  await absences.scrollIntoViewIfNeeded();
  await d.caption('Отсутствия команды стол берёт из раздела «Ресурсы»');
  await d.show(absences);
  await d.waitVoice();

  // Тема.
  await page.evaluate(() => window.scrollTo({ top: 0 }));
  const themeToggle = page.locator('.desk-theme-toggle');
  await d.click(themeToggle, 'Переключатель темы — светлая и тёмная');
  await page.mouse.move(1436, 450);
  await d.show(page.locator('.desk-header'));
  await d.waitVoice();

  await d.caption('Готово', 2200);
  await d.save('desk-analyst-use');
});
