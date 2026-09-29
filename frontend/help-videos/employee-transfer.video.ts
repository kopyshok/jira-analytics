// Ролик «Как перевести сотрудника в другую группу»: «Команда Эта» (команда с
// делением на группы) → карточка сотрудника → блок «Группы» → «Перевести в
// группу» (новая группа, дата) → история группы обновилась. → Сценарии:
// ресурс по группам и метка «в группе с …» учли перевод.
import { expect, test } from '@playwright/test';
import dayjs from 'dayjs';
import { Director } from './director.ts';

const TEAM = 'Команда Эта';
const EMPLOYEE_ID = '64deff1a-6423-4d75-a001-0f767d4d3bc0'; // Куликова Галина
const EMPLOYEE_NAME = 'Куликова Галина';
const NEW_GROUP = 'Группа 1';
const TRANSFER_DATE = '2026-11-01';

test('employee-transfer', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  const api = `${String(test.info().config.metadata.backendUrl)}/api/v1`;
  expect((await page.request.put(`${api}/auth/me/teams`, { data: { teams: [TEAM], subgroups: [] } })).ok()).toBeTruthy();

  await d.open('/capacity', 'Как перевести сотрудника в другую группу');
  const table = page.locator('[data-tour="capacity-team-table"]');
  await expect(table.locator('tbody tr.capacity-emp-row', { hasText: EMPLOYEE_NAME })).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1100);

  await d.click(page.locator('.side-item', { hasText: 'Ресурсы' }), 'Откройте раздел «Ресурсы»');

  const departedSwitch = page.locator('[data-tour="capacity-toolbar"]').getByRole('switch').nth(2);
  await d.caption('Переключатель «Показывать выбывших» — если человек уже ушёл из команды');
  await d.click(departedSwitch, '');
  await d.pause(500);
  await d.click(departedSwitch, '');

  const row = table.locator('tbody tr.capacity-emp-row', { hasText: EMPLOYEE_NAME });
  await d.click(row.getByText(EMPLOYEE_NAME, { exact: true }), 'Откройте карточку сотрудника');

  const drawer = page.locator('.ant-drawer-open');
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText(TEAM).first()).toBeVisible();

  const groupsHeading = drawer.getByText('Группы', { exact: true });
  await d.caption('Блок «Группы» — в какой группе сотрудник работает и с какого числа');
  await d.show(groupsHeading);
  await d.pause(1000);

  const currentRecord = drawer.getByText(/с начала участия/);
  await expect(currentRecord).toBeVisible();
  await d.caption('Сейчас весь квартал сотрудник в «Группа 3»');
  await d.show(currentRecord);
  await d.pause(1000);

  await d.click(drawer.getByRole('button', { name: 'Перевести в группу' }), 'Нажмите «Перевести в группу»');
  const modal = page.locator('.ant-modal', { hasText: 'Перевести в группу' });
  await expect(modal).toBeVisible();

  await d.click(modal.locator('.ant-picker-input'), 'Дата перевода');
  const dropdown = page.locator('.ant-picker-dropdown:visible');
  const target = dayjs(TRANSFER_DATE);
  for (let i = 0; i < 12 && !(await dropdown.locator(
    `td.ant-picker-cell-in-view[title="${target.format('YYYY-MM-DD')}"]`).count()); i++) {
    await dropdown.locator('.ant-picker-header-next-btn').click();
  }
  await d.click(dropdown.locator(`td.ant-picker-cell-in-view[title="${target.format('YYYY-MM-DD')}"]`));
  await expect(dropdown).toHaveCount(0);

  await d.click(modal.locator('.ant-select').filter({ hasText: 'Группа' }), 'Новая группа');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: new RegExp(`^${NEW_GROUP}$`) }));

  await d.click(modal.getByRole('button', { name: 'Сохранить' }), 'Сохраните');
  await expect(page.getByText('Сотрудник переведён')).toBeVisible();
  await expect(modal).toBeHidden();
  await page.mouse.move(1100, 180);

  const newRecord = drawer.getByText(new RegExp(`с ${target.format('DD.MM.YYYY')}`));
  await expect(newRecord).toBeVisible();
  await d.caption('С этой даты часы сотрудника идут новой группе, до неё — прежней');
  await d.show(groupsHeading, newRecord);
  await d.pause(1400);

  await d.click(drawer.locator('.ant-drawer-close'), 'Закройте карточку');
  await expect(drawer).toBeHidden();

  // Сценарии команды: ресурс по группам поделился между старой и новой группой.
  await d.click(page.locator('.side-item', { hasText: 'Сценарии' }), 'Загляните в сценарий команды');
  const scenarioSelect = page.locator('[data-tour="planning-scenario-select"]');
  await d.click(scenarioSelect, 'Выберите черновик квартала');
  await d.click(page.locator('.ant-select-dropdown:visible .ant-select-item-option', { hasText: /Q4 2026/ }));

  const panel = page.locator('[data-tour="planning-capacity-panel"]');
  await expect(panel).toBeVisible();
  const empInPanel = panel.getByText(EMPLOYEE_NAME).first();
  await expect(empInPanel).toBeVisible({ timeout: 15_000 });
  const groupTag = panel.getByText(/в группе (с|до) \d{2}\.\d{2}/).first();
  await expect(groupTag).toBeVisible({ timeout: 15_000 });
  await empInPanel.scrollIntoViewIfNeeded();
  await d.caption('«Ресурс по группам» сам поделил часы сотрудника между группами');
  await d.show(empInPanel, groupTag);
  await d.pause(1800);

  await d.caption('Готово', 2200);
  await d.save('employee-transfer');

  // Уборка: снимаем перевод и возвращаем шапку на «Команда Альфа» без групп —
  // так её ждут остальные ролики.
  await page.request.delete(
    `${api}/teams/employees/${EMPLOYEE_ID}/subgroup-shares?team=${encodeURIComponent(TEAM)}&valid_from=${TRANSFER_DATE}`,
  );
  await page.request.put(`${api}/auth/me/teams`, { data: { teams: ['Команда Альфа'], subgroups: [] } });
});
