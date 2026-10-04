// Ролик «Как отделить служебные эпики от инициатив и настроить планирование»:
// «Настройки» → «Правила иерархии» — новое правило («Только с родителем», «Считать
// контейнером» выключено), стрелки порядка → «Целевые задачи»: служебный эпик строкой
// под инициативой с выключенным «В план» → «Планирование»: мультикомандные RFA только
// по эпикам, «ОПЭ не планируем начиная с квартала» (изменили и вернули).
// От имени демо-администратора. В конце правило удалено, приоритеты и настройки возвращены.
import { expect, type PlaywrightWorkerArgs, test, type TestInfo } from '@playwright/test';
import { ADMIN_STATE } from './admin.ts';
import { Director } from './director.ts';

test.use({ storageState: ADMIN_STATE });

const TEAM = 'Команда Альфа';
const PROJECT = 'PRH';
const OPO_KEY = 'planning_opo_cutoff';
const MULTI_KEY = 'planning_multi_team_by_epics';

interface Rule {
  id: string;
  priority: number;
  description: string | null;
}

let originalPriorities: Rule[] = [];
let originalCutoff: string | null = null;
let originalMulti: string | null = null;

async function ctx(playwright: PlaywrightWorkerArgs['playwright'], testInfo: TestInfo) {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({ storageState: ADMIN_STATE });
  return { api, request };
}

test.beforeAll(async ({ playwright }, testInfo) => {
  const { api, request } = await ctx(playwright, testInfo);
  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  originalPriorities = ((await (await request.get(`${api}/hierarchy-rules`)).json()) as Rule[]).map((r) => ({
    id: r.id,
    priority: r.priority,
    description: r.description,
  }));
  originalCutoff = ((await (await request.get(`${api}/settings/generic/${OPO_KEY}`)).json()) as { value: string | null }).value;
  originalMulti = ((await (await request.get(`${api}/settings/generic/${MULTI_KEY}`)).json()) as { value: string | null }).value;
  await request.put(`${api}/settings/generic`, { data: { key: MULTI_KEY, value: 'true' } });
  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  const { api, request } = await ctx(playwright, testInfo);
  const known = new Set(originalPriorities.map((o) => o.id));
  const rules = (await (await request.get(`${api}/hierarchy-rules`)).json()) as Rule[];
  for (const r of rules.filter((r) => !known.has(r.id))) {
    await request.delete(`${api}/hierarchy-rules/${r.id}`);
  }
  // Стрелки перенумеровали приоритеты всех правил — возвращаем прежние.
  for (const o of originalPriorities) {
    await request.patch(`${api}/hierarchy-rules/${o.id}`, { data: { priority: o.priority } });
  }
  await request.put(`${api}/settings/generic`, { data: { key: OPO_KEY, value: originalCutoff ?? '' } });
  await request.put(`${api}/settings/generic`, { data: { key: MULTI_KEY, value: originalMulti ?? 'true' } });
  await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } });
  await request.dispose();
});

test('settings-hierarchy-planning', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  // Без доступа к Jira список типов задач не загрузился бы и в кадре было бы предупреждение.
  await page.route('**/api/v1/sync/jira-issuetypes', (route) =>
    route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(['Эпик', 'История', 'Задача', 'Подзадача', 'Баг', 'Инициатива']),
    }));

  await d.open('/settings#hierarchy', 'Как отделить служебные эпики от инициатив');
  const addRule = page.getByRole('button', { name: /Правило$/ });
  await expect(addRule).toBeVisible({ timeout: 20_000 });
  await expect(page.locator('tr.ant-table-row').first()).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  const menuItem = (label: string) => page.locator('.ant-menu-item', { hasText: label });

  await d.click(addRule, 'Нажмите «Правило»');
  const drawer = page.locator('.ant-drawer-open');
  await expect(drawer).toBeVisible();
  const item = (label: string) => drawer.locator('.ant-form-item', { hasText: label });

  const prio = item('Приоритет').locator('.ant-input-number-input');
  await d.click(prio, 'Приоритет — чем меньше число, тем раньше проверка');
  await prio.pressSequentially('4', { delay: 90 });

  await d.click(item('Проект').locator('.ant-select'), 'Проект — тот, где заводятся служебные эпики');
  await page.keyboard.type(PROJECT, { delay: 100 });
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: PROJECT }).first());

  await d.click(item('Тип задачи').locator('.ant-select'), 'Тип задачи — «Эпик»');
  await page.keyboard.type('Эпик', { delay: 100 });
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: /^Эпик$/ }).first());

  await d.click(item('Родитель').locator('.ant-select'), 'Родитель — «Только с родителем»');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: 'Только с родителем' }));

  await d.click(item('Считать контейнером').getByRole('switch'), 'Выключите «Считать контейнером»');
  await expect(item('Считать контейнером').getByRole('switch')).not.toBeChecked();
  await d.click(drawer.getByRole('button', { name: 'Сохранить' }), 'Сохраните');
  await expect(drawer).toBeHidden();
  await page.mouse.move(1300, 120);

  const ruleRow = page.locator('tr.ant-table-row', { has: page.locator('.ant-tag', { hasText: 'только с родителем' }) }).first();
  await expect(ruleRow).toBeVisible({ timeout: 10_000 });
  await d.caption('Правило встало первым — оно проверяется раньше остальных');
  await d.show(ruleRow);
  await d.pause(800);

  const down = ruleRow.locator('button:has(.anticon-arrow-down)');
  await d.click(down, 'Стрелки меняют порядок правил');
  await d.click(page.locator('tr.ant-table-row').nth(1).locator('button:has(.anticon-arrow-up)'), 'И вернём правило наверх');
  await page.mouse.move(1300, 120);

  // === Целевые задачи ===
  await d.waitVoice();
  await d.click(page.locator('.side-item', { hasText: 'Целевые задачи' }), 'Смотрим «Целевые задачи»');
  const tag = page.locator('.ant-tag', { hasText: 'Дискавери' }).first();
  await expect(tag).toBeVisible({ timeout: 30_000 });
  await tag.scrollIntoViewIfNeeded();
  await d.caption('Служебный эпик — строкой под инициативой, с меткой «Дискавери»');
  await d.show(tag);
  await d.pause(2500);
  const bodyRow = page.locator('tr.ant-table-row', { has: tag }).first();
  const inPlan = bodyRow.getByRole('switch').first();
  if (await inPlan.count()) {
    await d.caption('Переключатель «В план» у него выключен');
    await d.show(inPlan);
    await d.pause(2000);
  }

  // === Планирование ===
  await d.waitVoice();
  await d.click(page.locator('.side-item', { hasText: 'Настройки' }), 'Вернёмся в «Настройки» — экран «Планирование»');
  await page.evaluate(() => window.scrollTo(0, 0));
  await d.click(menuItem('Планирование'));
  const planningCard = page.locator('.ant-card', { hasText: 'Мультикомандные RFA' });
  await expect(planningCard).toBeVisible({ timeout: 20_000 });
  const multi = planningCard.getByRole('switch').first();
  await d.caption('Мультикомандную инициативу команды планируют только по своим эпикам');
  await d.show(multi);
  await d.pause(2200);
  const cutoff = planningCard.locator('.ant-select');
  await d.caption('«ОПЭ не планируем начиная с квартала» — выберите квартал');
  await d.show(cutoff);
  await d.pause(1800);
  await d.click(cutoff);
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: '1 кв. 2027' }));
  await expect(page.getByText('Сохранено').first()).toBeVisible({ timeout: 10_000 });
  await page.mouse.move(1300, 120);
  await d.caption('С этого квартала этап ОПЭ пропадёт из планов, часы уйдут в анализ и разработку');
  await d.show(planningCard);
  await d.pause(2500);
  await d.click(cutoff, 'Вернём прежний квартал');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: '4 кв. 2026' }));
  await expect(cutoff).toContainText('4 кв. 2026');
  await page.mouse.move(1300, 120);
  await d.pause(800);

  await d.caption('Готово', 2200);
  await d.save('settings-hierarchy-planning');
});
