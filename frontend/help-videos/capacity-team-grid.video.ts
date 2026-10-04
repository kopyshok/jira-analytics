// Ролик «Как читать план и факт команды»: Ресурсы → вкладка «Команда» →
// «Уточнить период» (прошлый квартал) → «Факт» и «%» → цвета процента →
// «Свернуть все» / «Развернуть все» → «Показывать выбывших» и «Показывать выключенных» →
// фильтр по сотруднику → дни участия режут план и факт → «Экспорт в Excel» (только нажатие).
//
// Подготовка (в beforeAll, до записи): у одного сотрудника «Команда Альфа» ставится дата
// выбытия, другой выключается — иначе в демо-базе нечего показать переключателям.
// В afterAll всё возвращается.
import { type APIRequestContext, expect, test } from '@playwright/test';
import dayjs from 'dayjs';
import { Director } from './director.ts';

const TEAM = 'Команда Альфа';
const DEPARTED = 'Гуляев Пётр';
const SWITCHED_OFF = 'Назарова Ангелина';
/** Сотрудник, который вошёл в команду «Альфа» и вышел из неё посреди квартала — для связи с днями участия. */
const PARTIAL = 'Зайцев Артём';

type Emp = { id: string; display_name: string };

let ctx: APIRequestContext;
let api = '';
let departedId = '';
let switchedOffId = '';

test.beforeAll(async ({ playwright }) => {
  const info = test.info();
  api = `${String(info.config.metadata.backendUrl)}/api/v1`;
  ctx = await playwright.request.newContext({ storageState: info.project.use.storageState as string });
  const employees: Emp[] = await (await ctx.get(`${api}/employees`)).json();
  const find = (name: string) => {
    const e = employees.find((x) => x.display_name === name);
    if (!e) throw new Error(`В демо-базе нет сотрудника ${name}`);
    return e.id;
  };
  departedId = find(DEPARTED);
  switchedOffId = find(SWITCHED_OFF);

  expect((await ctx.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  const now = dayjs();
  expect((await ctx.put(`${api}/users/me/period`, {
    data: { year: now.year(), quarter: Math.floor(now.month() / 3) + 1 },
  })).ok()).toBeTruthy();

  // Выбыл в середине прошлого квартала: в нём часть плана есть, в текущем его уже нет.
  const prevQuarterStart = now.startOf('month').subtract(now.month() % 3, 'month').subtract(3, 'month');
  const left = prevQuarterStart.add(2, 'month').date(15).format('YYYY-MM-DD');
  expect((await ctx.patch(`${api}/employees/${departedId}/teams/${encodeURIComponent(TEAM)}/left-at`, {
    data: { left_at: left },
  })).ok()).toBeTruthy();
  expect((await ctx.patch(`${api}/employees/${switchedOffId}`, { data: { is_active: false } })).ok()).toBeTruthy();
});

test.afterAll(async () => {
  await ctx.patch(`${api}/employees/${departedId}/teams/${encodeURIComponent(TEAM)}/left-at`, { data: { left_at: null } });
  await ctx.patch(`${api}/employees/${switchedOffId}`, { data: { is_active: true } });
  await ctx.dispose();
});

test('capacity-team-grid', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const now = dayjs();
  const curQ = Math.floor(now.month() / 3) + 1;
  const prevQ = curQ === 1 ? 4 : curQ - 1;

  await d.open('/capacity', 'Как читать план и факт команды');
  const table = page.locator('[data-tour="capacity-team-table"]');
  const toolbar = page.locator('[data-tour="capacity-toolbar"]');
  await expect(table.locator('tbody tr.capacity-emp-row').first()).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1100);

  await d.click(page.locator('.side-item', { hasText: 'Ресурсы' }), 'Откройте раздел «Ресурсы»');
  await d.caption('Вкладка «Команда» — доступные часы по месяцам квартала');
  await d.show(table);
  await d.waitVoice();

  // Прошлый квартал — «Уточнить период», остальные разделы остаются на прежнем.
  await d.click(page.getByRole('checkbox', { name: 'Уточнить период' }), 'Чтобы заглянуть в другой квартал — «Уточнить период»');
  const quarterSelect = page.locator('[data-tour="capacity-period-quarter"]');
  await d.click(quarterSelect);
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: new RegExp(`^Q${prevQ}$`) }));
  await expect(table.locator('tbody tr.capacity-emp-row').first()).toBeVisible();
  await page.mouse.move(1100, 200);
  await d.caption('Другие разделы останутся на прежнем периоде');
  await d.pause(600);

  // «Факт» и «%».
  const factSwitch = toolbar.getByRole('switch').nth(0);
  const pctSwitch = toolbar.getByRole('switch').nth(1);
  await d.waitVoice();
  await d.click(factSwitch, '«Факт» — сколько часов списано в Jira');
  await expect(table.locator('thead th', { hasText: 'Факт' }).first()).toBeVisible();
  await d.click(pctSwitch, '«%» — какую долю плана заняли списания');
  await expect(table.locator('thead th', { hasText: '%' }).first()).toBeVisible();
  await page.mouse.move(1100, 200);
  await d.show(table.locator('thead'));
  await d.waitVoice();

  // Цвета процента.
  const coloured = table.locator('tbody td span[style*="color"]').filter({ hasText: '%' });
  if (await coloured.count()) {
    await d.caption('Зелёный процент — план выполнен, красный — перегруз, серый — недогруз');
    await d.show(coloured.first());
    await d.waitVoice();
  }

  // Строки команд.
  const collapseAll = page.getByRole('button', { name: 'Свернуть все' });
  await d.click(collapseAll, '«Свернуть все» оставит только строки команд');
  await expect(table.locator('tbody tr.capacity-emp-row')).toHaveCount(0);
  await d.show(table.locator('tbody tr.capacity-team-row').first());
  await d.waitVoice();
  await d.click(page.getByRole('button', { name: 'Развернуть все' }), '«Развернуть все» вернёт сотрудников');
  await expect(table.locator('tbody tr.capacity-emp-row').first()).toBeVisible();

  // Выбывшие и выключенные.
  const departedSwitch = toolbar.getByRole('switch').nth(2);
  const inactiveSwitch = toolbar.getByRole('switch').nth(3);
  await d.waitVoice();
  await d.click(departedSwitch, '«Показывать выбывших» — тех, кто уже ушёл из команды');
  const departedRow = table.locator('tbody tr.capacity-emp-row', { hasText: DEPARTED });
  await expect(departedRow).toBeVisible();
  await page.mouse.move(1100, 200);
  await departedRow.evaluate((el) => el.scrollIntoView({ block: 'center' }));
  await d.show(departedRow);
  await d.waitVoice();
  await d.click(inactiveSwitch, '«Показывать выключенных» — тех, кого выключили в карточке');
  const offRow = table.locator('tbody tr.capacity-emp-row', { hasText: SWITCHED_OFF });
  await expect(offRow).toBeVisible();
  await page.mouse.move(1100, 200);
  await offRow.evaluate((el) => el.scrollIntoView({ block: 'center' }));
  await d.show(offRow);
  await d.waitVoice();

  // Фильтр по сотруднику.
  const empFilter = toolbar.locator('.ant-select').first();
  await d.click(empFilter, 'Фильтр по сотруднику оставит в таблице только выбранных');
  await empFilter.locator('input').pressSequentially('Зайц', { delay: 90 });
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: PARTIAL }));
  await page.keyboard.press('Escape');
  await expect(table.locator('tbody tr.capacity-emp-row')).toHaveCount(1);
  await page.mouse.move(1100, 200);

  // Связь: дни участия в команде режут план и факт.
  const partialRow = table.locator('tbody tr.capacity-emp-row', { hasText: PARTIAL });
  await d.caption('Дни участия в команде режут и план, и факт');
  await d.show(partialRow);
  await d.waitVoice();

  // Экспорт — только нажатие на кнопку.
  const exportBtn = page.getByRole('link', { name: 'Экспорт в Excel' }).or(page.getByRole('button', { name: 'Экспорт в Excel' }));
  await d.caption('«Экспорт в Excel» выгрузит эту сетку в файл');
  await d.point(exportBtn.first());
  await d.waitVoice();

  await d.caption('Готово', 2200);
  await d.save('capacity-team-grid');
});
