// Ролик «Как подготовить календарь и причины отсутствий»: «Настройки» → «Производственный
// календарь» — год, «Добавить день» (корпоративный выходной), правка дня → «Причины
// отсутствий» — новая причина (цвет, «Плановое») → «Ресурсы» → «Отсутствия»: отпуск с новой
// причиной на карте. Загрузка календаря с внешнего сайта не нажимается.
// От имени демо-администратора. В конце день, причина и отсутствие убраны.
import { expect, type Locator, type PlaywrightWorkerArgs, test, type TestInfo } from '@playwright/test';
import dayjs from 'dayjs';
import { ADMIN_STATE } from './admin.ts';
import { Director } from './director.ts';

test.use({ storageState: ADMIN_STATE });

const TEAM = 'Команда Альфа';
const CAL_DATE = '2026-01-14';
const CAL_DATE_RU = '14.01.2026';
const REASON_CODE = 'study_leave';
const REASON_LABEL = 'Учёба';
const REASON_COLOR = '#13c2c2';

interface Reason {
  id: string;
  code: string;
}

let absenceId = '';

async function ctx(playwright: PlaywrightWorkerArgs['playwright'], testInfo: TestInfo) {
  const api = `${String(testInfo.config.metadata.backendUrl)}/api/v1`;
  const request = await playwright.request.newContext({ storageState: ADMIN_STATE });
  return { api, request };
}

/** Кликнуть по дню в открытом календаре, долистав до нужного месяца. */
async function pickDay(dropdown: Locator, day: dayjs.Dayjs, d: Director): Promise<void> {
  for (let i = 0; i < 24; i++) {
    const cell = dropdown.locator(`td.ant-picker-cell-in-view[title="${day.format('YYYY-MM-DD')}"]`);
    if (await cell.count()) {
      await d.click(cell.first());
      return;
    }
    await dropdown.locator('.ant-picker-header-next-btn').last().click();
  }
  throw new Error(`Не нашли дату ${day.format('YYYY-MM-DD')} в календаре`);
}

test.beforeAll(async ({ playwright }, testInfo) => {
  const { api, request } = await ctx(playwright, testInfo);
  expect((await request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();
  const now = new Date();
  expect((await request.put(`${api}/users/me/period`, {
    data: { year: now.getFullYear(), quarter: Math.floor(now.getMonth() / 3) + 1 },
  })).ok()).toBeTruthy();
  // Остаток прошлой съёмки: причина с тем же кодом.
  const reasons = (await (await request.get(`${api}/capacity/absence-reasons`)).json()) as Reason[];
  const stale = reasons.find((r) => r.code === REASON_CODE);
  if (stale) await request.delete(`${api}/capacity/absence-reasons/${stale.id}`);
  await request.delete(`${api}/production-calendar/${CAL_DATE}`);
  await request.dispose();
});

test.afterAll(async ({ playwright }, testInfo) => {
  const { api, request } = await ctx(playwright, testInfo);
  // Порядок важен: сначала отпуск, потом причина.
  if (absenceId) await request.delete(`${api}/capacity/absences/${absenceId}`);
  const reasons = (await (await request.get(`${api}/capacity/absence-reasons`)).json()) as Reason[];
  const created = reasons.find((r) => r.code === REASON_CODE);
  if (created) await request.delete(`${api}/capacity/absence-reasons/${created.id}`);
  // Своего дня больше нет: без записи рабочий день считается по общему правилу, как было.
  await request.delete(`${api}/production-calendar/${CAL_DATE}`);
  await request.dispose();
});

test('settings-calendar-reasons', async ({ page }) => {
  const d = new Director(page);
  await d.install();
  const api = `${String(test.info().config.metadata.backendUrl)}/api/v1`;

  await d.open('/settings#calendar', 'Как подготовить календарь и причины отсутствий');
  const addDay = page.getByRole('button', { name: 'Добавить день' });
  await expect(addDay).toBeVisible({ timeout: 20_000 });
  await expect(page.locator('tr.ant-table-row').first()).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  const menuItem = (label: string) => page.locator('.ant-menu-item', { hasText: label });

  await d.caption('Сверху — год календаря. Кнопка загрузки подтянет официальный календарь');
  await d.show(page.locator('.ant-input-number').first(), page.getByRole('button', { name: /Загрузить с/ }));
  await d.pause(1200);

  await d.click(addDay, 'Свой выходной компании — «Добавить день»');
  const modal = page.locator('.ant-modal', { hasText: 'Добавить день' });
  await expect(modal).toBeVisible();
  const dateInput = modal.locator('.ant-picker input');
  await d.type(dateInput, CAL_DATE_RU, 'Укажите дату');
  await dateInput.press('Enter');
  await d.type(modal.locator('#note'), 'Корпоративный выходной', 'Тип — «Праздник», примечание — словами');
  await d.click(modal.locator('.ant-modal-footer .ant-btn-primary'), 'Сохраните');
  await expect(modal).toBeHidden();
  await page.mouse.move(1300, 120);

  const dayRow = page.locator('tr.ant-table-row', { hasText: CAL_DATE_RU });
  await expect(dayRow).toBeVisible({ timeout: 10_000 });
  await dayRow.evaluate((el) => el.scrollIntoView({ block: 'center' }));
  await d.caption('День добавлен с пометкой «ручной», норма часов — ноль');
  await d.show(dayRow);
  await d.pause(1000);

  await d.click(dayRow.locator('button:has(.anticon-edit)'), 'Карандаш в строке правит день');
  const editModal = page.locator('.ant-modal', { hasText: 'Изменить день' });
  await expect(editModal).toBeVisible();
  const note = editModal.locator('#note');
  await d.click(note);
  await note.press('Control+A');
  await note.pressSequentially('Корпоративный выходной по приказу', { delay: 70 });
  await d.pause(500);
  await d.caption('Поправьте примечание и сохраните');
  await d.click(editModal.locator('.ant-modal-footer .ant-btn-primary'));
  await expect(editModal).toBeHidden();
  await page.mouse.move(1300, 120);
  await expect(dayRow).toContainText('по приказу');
  await d.show(dayRow);
  await d.pause(800);

  // === Причины отсутствий ===
  await d.waitVoice();
  await d.click(menuItem('Причины отсутствий'), 'Теперь — «Причины отсутствий»');
  const addReason = page.getByRole('button', { name: 'Добавить причину' });
  await expect(addReason).toBeVisible({ timeout: 15_000 });
  await d.click(addReason, 'Нажмите «Добавить причину»');
  const reasonModal = page.locator('.ant-modal', { hasText: 'Новая причина' });
  await expect(reasonModal).toBeVisible();
  await d.type(reasonModal.locator('#code'), REASON_CODE, 'Короткий код латиницей');
  await d.type(reasonModal.locator('#label'), REASON_LABEL, 'Название — как увидят в списках');
  await d.click(reasonModal.locator('#is_planned'), '«Плановое» — для отпусков и учёбы');
  const color = reasonModal.locator('#color');
  await d.click(color, 'Цвет на карте отсутствий');
  await color.press('Control+A');
  await color.pressSequentially(REASON_COLOR, { delay: 80 });
  await d.pause(400);
  await d.click(reasonModal.locator('.ant-modal-footer .ant-btn-primary'), 'Сохраните');
  await expect(reasonModal).toBeHidden();
  await page.mouse.move(1300, 120);
  const reasonRow = page.locator('tr.ant-table-row', { hasText: REASON_CODE });
  await expect(reasonRow).toBeVisible({ timeout: 10_000 });
  await d.caption('Причина появилась в справочнике');
  await d.show(reasonRow);
  await d.pause(800);

  // === Ресурсы → Отсутствия ===
  await d.waitVoice();
  await d.click(page.locator('.side-item', { hasText: 'Ресурсы' }), 'Теперь внесём отпуск с новой причиной — «Ресурсы»');
  await d.click(page.locator('[data-tour="capacity-tab-absences"]'), 'Вкладка «Отсутствия»');
  const row = page.locator('[data-tour="capacity-absence-table"] tbody tr.ant-table-row').first();
  await expect(row).toBeVisible({ timeout: 15_000 });
  const person = (await row.locator('td').first().innerText()).trim();
  await d.click(row.getByRole('button', { name: 'добавить' }), 'Нажмите «добавить» у сотрудника');
  const absModal = page.locator('.ant-modal', { hasText: 'Новое отсутствие' });
  await expect(absModal).toBeVisible();
  await d.click(absModal.locator('.ant-form-item', { hasText: 'Причина' }).locator('.ant-select'), 'Выберите новую причину');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: REASON_LABEL }));

  const start = dayjs().add(1, 'day');
  const end = start.add(3, 'day');
  await d.click(absModal.locator('.ant-picker-input').first(), 'Укажите даты');
  const dropdown = page.locator('.ant-picker-dropdown:visible');
  await pickDay(dropdown, start, d);
  await pickDay(dropdown, end, d);
  await expect(dropdown).toHaveCount(0);
  const [createResp] = await Promise.all([
    page.waitForResponse((r) => r.url().includes('/capacity/absences') && r.request().method() === 'POST'),
    d.click(absModal.locator('.ant-modal-footer .ant-btn-primary'), 'Сохраните'),
  ]);
  absenceId = ((await createResp.json()) as { id: string }).id;
  await expect(absModal).toBeHidden();
  await page.mouse.move(1300, 180);

  const tag = row.locator('.ant-tag', { hasText: REASON_LABEL });
  await expect(tag).toBeVisible();
  await d.caption(`Отсутствие встало на карту цветом новой причины`);
  await d.show(page.locator('[data-tour="capacity-absence-heatmap"]'));
  await d.pause(1500);
  void person;
  void api;

  await d.caption('Готово', 2200);
  await d.save('settings-calendar-reasons');
});
