// Ролик «Как внести отпуск»: Ресурсы → Отсутствия → «добавить» у сотрудника →
// причина и даты → сохранить → отпуск в таблице и на карте отсутствий.
import { expect, test } from '@playwright/test';
import dayjs from 'dayjs';
import { Director } from './director.ts';

test('absence-add', async ({ page }) => {
  // Отпуск — две рабочие недели в следующем месяце: он всегда виден в правой
  // половине календаря без перелистывания. Период страницы — квартал этого месяца.
  const month = dayjs().add(1, 'month').startOf('month');
  let start = month.date(8);
  while (start.day() !== 1) start = start.add(1, 'day');
  const end = start.add(11, 'day');
  const quarter = Math.floor(month.month() / 3) + 1;
  const quarterStart = month.month((quarter - 1) * 3).startOf('month');

  const d = new Director(page);
  await d.install();

  const api = String(test.info().config.metadata.backendUrl);
  const period = await page.request.put(`${api}/api/v1/users/me/period`, {
    data: { year: month.year(), quarter, month: month.month() + 1 },
  });
  expect(period.ok()).toBeTruthy();

  await d.open('/capacity', 'Как внести отпуск');
  await expect(page.locator('[data-tour="capacity-team-table"] tbody tr.ant-table-row').first()).toBeVisible();
  await expect(page.getByText(`Q${quarter} (`).first()).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  await d.click(page.locator('.side-item', { hasText: 'Ресурсы' }), 'Откройте раздел «Ресурсы»');
  await d.click(page.locator('[data-tour="capacity-tab-absences"]'), 'Перейдите на вкладку «Отсутствия»');

  const heatmap = page.locator('[data-tour="capacity-absence-heatmap"]');
  await expect(heatmap).toBeVisible();
  await d.caption('Сверху — карта отсутствий команды');
  await d.show(heatmap);
  await d.pause(1400);

  const row = page.locator('[data-tour="capacity-absence-table"] tbody tr.ant-table-row').nth(1);
  const employee = (await row.locator('td').first().innerText()).trim();
  await d.click(row.getByRole('button', { name: 'добавить' }), 'Нажмите «добавить» у сотрудника');

  const modal = page.locator('.ant-modal', { hasText: 'Новое отсутствие' });
  await expect(modal).toBeVisible();
  await d.pause(400);
  await d.click(modal.locator('.ant-form-item', { hasText: 'Причина' }).locator('.ant-select'), 'Выберите причину');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: /^Отпуск$/ }));

  await d.click(modal.locator('.ant-picker-input').first(), 'Укажите даты: начало и конец');
  const cell = (day: dayjs.Dayjs) =>
    page.locator(`.ant-picker-dropdown:visible td.ant-picker-cell-in-view[title="${day.format('YYYY-MM-DD')}"]`);
  await d.click(cell(start));
  await d.click(cell(end));
  await expect(page.locator('.ant-picker-dropdown:visible')).toHaveCount(0);

  await d.click(modal.locator('.ant-modal-footer .ant-btn-primary'), 'Сохраните');
  await expect(modal).toBeHidden();
  // Настоящая мышь осталась над картой — уводим, чтобы не всплывали подсказки ячеек.
  await page.mouse.move(1100, 180);

  const tag = row.locator('.ant-tag', { hasText: `${start.format('DD.MM')}—${end.format('DD.MM')}` });
  await expect(tag).toBeVisible();
  await d.caption('Отпуск появился в строке сотрудника');
  await d.show(tag);
  await d.pause(1200);

  const heatRow = heatmap.locator('div[style*="contents"]', { hasText: employee });
  const dayCell = (day: dayjs.Dayjs) => heatRow.locator(':scope > div').nth(1 + day.diff(quarterStart, 'day'));
  await d.caption('…и на карте отсутствий');
  await d.show(dayCell(start), dayCell(end));
  await d.pause(1400);

  await d.caption('Готово', 2200);
  await d.save('absence-add');
});
