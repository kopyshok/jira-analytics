// Ролик «Как внести отпуск и увидеть сдвиг плана»: Ресурсы → Отсутствия →
// «добавить» разработчику, у которого в ресурсном плане квартала уже стоит
// фаза разработки, → причина и даты → карта отсутствий. → Сценарии
// (утверждённый квартал): полоса «Доступность изменилась» — отпуск снизил
// доступные часы. → Ресурс. планир.: «Распределить» — фаза разработки
// сдвинулась, на полосе видна штриховка отпуска.
import { expect, test, type Locator } from '@playwright/test';
import dayjs from 'dayjs';
import { Director } from './director.ts';
import { phaseBar, prepareQuarterPlan } from './rp-setup.ts';

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

test('absence-add', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const api = `${String(test.info().config.metadata.backendUrl)}/api/v1`;

  // Подготовка до первого кадра: свежий пересчитанный план квартала и в нём —
  // разработчик с фазой «Разработка». Отпуск ляжет прямо на начало этой фазы.
  const { rp, scenario, plan, assignments } = await prepareQuarterPlan(page);
  const dev = assignments.find((a) => a.phase === 'dev' && a.employee_id && a.start_date);
  if (!dev) throw new Error('В плане нет фазы разработки с исполнителем');

  const employees: { id: string; display_name: string }[] = await (
    await page.request.get(`${api}/employees`)
  ).json();
  const employee = employees.find((e) => e.id === dev.employee_id);
  if (!employee) throw new Error('Не найден сотрудник фазы разработки');

  const reasons: { id: string; label: string }[] = await (
    await page.request.get(`${api}/capacity/absence-reasons`)
  ).json();
  const vacation = reasons.find((r) => r.label === 'Отпуск');
  if (!vacation) throw new Error('В справочнике нет причины «Отпуск»');

  const start = dayjs(dev.start_date);
  const end = start.add(9, 'day');

  // Страница «Ресурсы» смотрит на квартал сценария, а не на текущий.
  const quarterNum = Number(String(scenario.quarter).replace('Q', ''));
  expect((await page.request.put(`${api}/users/me/period`, {
    data: { year: scenario.year, quarter: quarterNum },
  })).ok()).toBeTruthy();

  const devBar = phaseBar(page, dev);

  await d.open('/capacity', 'Как внести отпуск и увидеть сдвиг плана');
  await expect(page.locator('[data-tour="capacity-team-table"] tbody tr.ant-table-row').first()).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1200);

  await d.click(page.locator('.side-item', { hasText: 'Ресурсы' }), 'Откройте раздел «Ресурсы»');
  await d.click(page.locator('[data-tour="capacity-tab-absences"]'), 'Перейдите на вкладку «Отсутствия»');

  const row = page.locator('[data-tour="capacity-absence-table"] tbody tr.ant-table-row', {
    hasText: employee.display_name,
  });
  await expect(row).toBeVisible();
  await d.caption(`Отпуск разработчику — ${employee.display_name}`);
  await d.show(row);
  await d.pause(700);

  await d.click(row.getByRole('button', { name: 'добавить' }), 'Нажмите «добавить»');
  const modal = page.locator('.ant-modal', { hasText: 'Новое отсутствие' });
  await expect(modal).toBeVisible();
  await d.click(modal.locator('.ant-form-item', { hasText: 'Причина' }).locator('.ant-select'), 'Причина — «Отпуск»');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: /^Отпуск$/ }));

  await d.click(modal.locator('.ant-picker-input').first(), 'Даты — прямо на разработку по плану');
  const dropdown = page.locator('.ant-picker-dropdown:visible');
  await pickDay(dropdown, start, d);
  await pickDay(dropdown, end, d);
  await expect(dropdown).toHaveCount(0);

  const [createResp] = await Promise.all([
    page.waitForResponse((r) => r.url().includes('/capacity/absences') && r.request().method() === 'POST'),
    d.click(modal.locator('.ant-modal-footer .ant-btn-primary'), 'Сохраните'),
  ]);
  const createdAbsence: { id: string } = await createResp.json();
  await expect(modal).toBeHidden();
  await page.mouse.move(1100, 180);

  const tag = row.locator('.ant-tag', { hasText: `${start.format('DD.MM')}—${end.format('DD.MM')}` });
  await expect(tag).toBeVisible();
  await d.caption('Отпуск встал в календарь команды');
  await d.show(tag);
  await d.pause(600);

  // Те же отпуска — днями на тепловой карте.
  const heatmap = page.locator('[data-tour="capacity-absence-heatmap"]');
  await heatmap.scrollIntoViewIfNeeded();
  await d.caption('Те же отпуска — днями на карте');
  await d.show(heatmap);
  await d.pause(600);

  // Массовое добавление: окно только показываем, записи не создаём.
  await d.waitVoice();
  await d.click(page.locator('[data-tour="capacity-absence-bulk"]'), 'Нескольким сотрудникам сразу — «Массовое добавление»');
  const bulk = page.locator('.ant-modal', { hasText: 'Массовое добавление отсутствий' });
  await expect(bulk).toBeVisible();
  await page.mouse.move(1100, 180);
  await d.show(bulk.locator('.ant-modal-body'));
  await d.waitVoice();
  await d.click(bulk.getByRole('button', { name: 'Отмена' }));
  await expect(bulk).toBeHidden();

  // «Только внеплановые» прячет плановые причины — отпуск уходит из строки.
  const unplanned = page.locator('.ant-tabs-tabpane-active').getByRole('switch').first();
  await d.caption('«Только внеплановые» прячет плановые причины, например отпуск');
  await d.point(unplanned);
  await d.waitVoice();
  await d.click(unplanned);
  await expect(tag).toBeHidden();
  await d.show(row);
  await d.pause(900);
  await d.click(unplanned);
  await expect(tag).toBeVisible();
  await page.mouse.move(1100, 180);

  // Сценарии: утверждённый квартал уже не знает об этом отпуске — полоса
  // «Доступность изменилась» покажет расхождение.
  await d.click(page.locator('.side-item', { hasText: 'Сценарии' }), 'Загляните в сценарий квартала');
  const scenarioSelect = page.locator('[data-tour="planning-scenario-select"]');
  await d.click(scenarioSelect, 'Выберите утверждённый сценарий');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: scenario.name }));

  const driftHeader = page.getByText(/Доступность изменилась/);
  await expect(driftHeader).toBeVisible({ timeout: 15_000 });
  await d.caption('Отпуск уменьшил ресурс команды в сценарии');
  await d.show(driftHeader);
  await d.pause(1000);

  await d.click(driftHeader, 'Раскройте детали');
  const addedLine = page.getByText(/Добавлено:\s*Отпуск/);
  await expect(addedLine).toBeVisible();
  await d.show(addedLine);
  await d.pause(1400);

  // Ресурсное планирование: пересчёт обойдёт дни отпуска и сдвинет фазу.
  await d.click(page.locator('.side-item', { hasText: 'Ресурс. планир.' }), 'Перейдите в «Ресурс. планир.»');
  const rpSelect = page.locator('[data-tour="rp-scenario-select"]');
  await d.click(rpSelect, 'Откройте тот же сценарий');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: scenario.name }));

  await expect(devBar).toBeVisible({ timeout: 15_000 });
  await d.click(page.locator('[data-tour="rp-distribute"]'), 'Нажмите «Распределить»');
  await expect(page.locator('.ant-tag', { hasText: /^Готово$/ })).toBeVisible({ timeout: 60_000 });
  await expect(devBar).toBeVisible();
  await page.mouse.move(900, 120);

  await d.caption('…и сдвинул фазу разработки в плане');
  await d.show(devBar);
  await d.pause(1000);
  await d.caption('Штриховка на полосе — как раз дни отпуска');
  await d.point(devBar);
  await d.pause(1400);

  await d.caption('Готово', 2200);
  await d.save('absence-add');

  // Уборка: убираем отпуск и пересчитываем план, чтобы следующие ролики
  // видели команду такой же, какой она была до съёмки.
  await page.request.delete(`${api}/capacity/absences/${createdAbsence.id}`);
  await page.request.post(`${rp}/resource-plans/${plan.id}/compute`);
});
