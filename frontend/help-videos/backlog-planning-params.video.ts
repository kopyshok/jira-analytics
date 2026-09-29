// Ролик «Как задать параметры планирования»: Целевые задачи → у инициативы шестерёнка →
// вовлечённость и длительность по фазам → сохранить → значение отмечено как «вручную».
import { expect, test, type Locator } from '@playwright/test';
import { Director } from './director.ts';

test('backlog-planning-params', async ({ page }) => {
  const d = new Director(page);
  await d.install();

  // Боковая ссылка «Целевые задачи» ведёт на голый /backlog (без ?view=) — открываем
  // так и переключаемся на «Бэклог» кликом по вкладке, а не query-параметром в URL,
  // иначе редундантный клик по разделу в кадре сбросил бы вкладку обратно.
  await d.open('/backlog', 'Как задать параметры планирования');
  const pane = page.locator('[data-tour="backlog-tabs"] .ant-tabs-tabpane-active');
  await expect(pane.locator('tbody tr.ant-table-row').first()).toBeVisible();
  await d.pause(800);
  await d.poster();
  await d.pause(1500);

  await d.click(page.locator('.side-item', { hasText: 'Целевые задачи' }), 'Откройте раздел «Целевые задачи»');
  await d.click(
    page.locator('[data-tour="backlog-tabs"] .ant-tabs-tab', { hasText: 'Бэклог' }),
    'Перейдите на вкладку «Бэклог»',
  );

  // Верхняя по приоритету инициатива — своя шестерёнка есть у любой строки.
  const row = pane.locator('tbody tr.ant-table-row').first();
  await expect(row).toBeVisible();

  await d.click(row.locator('[data-tour="backlog-gear"]'), 'У инициативы — кнопка-шестерёнка');
  const modal = page.locator('.ant-modal', { hasText: 'Параметры планирования' });
  await expect(modal).toBeVisible();

  const phaseBlock = (label: string): Locator =>
    modal.getByRole('heading', { name: label, exact: true }).locator('xpath=..');

  // Клик + очистка + видимый ввод: InputNumber не очищается от pressSequentially одним нажатием.
  const setNumber = async (input: Locator, value: string, caption: string) => {
    await d.click(input, caption);
    await input.press('Control+A');
    await input.pressSequentially(value, { delay: 90 });
    await input.press('Tab');
    await d.pause(500);
  };

  await setNumber(phaseBlock('Анализ').locator('input').nth(0), '0.6', 'Измените вовлечённость на фазе анализа');
  await setNumber(phaseBlock('Разработка').locator('input').nth(1), '15', 'И срок фазы разработки');

  const listRefetched = page.waitForResponse(
    (r) => r.request().method() === 'GET' && /\/api\/v1\/backlog\?/.test(r.url()),
  );
  await d.click(modal.locator('.ant-modal-footer .ant-btn-primary'), 'Сохраните');
  await listRefetched;
  await expect(modal).toBeHidden();

  await d.click(row.locator('[data-tour="backlog-gear"]'), 'Откроем ещё раз — проверим, что сохранилось');
  await expect(modal).toBeVisible();
  const savedTag = phaseBlock('Анализ').getByText('вручную');
  await expect(savedTag).toBeVisible();
  await d.caption('Значение отмечено как ручное — не перезапишется само');
  await d.show(savedTag);
  await d.pause(1400);

  await d.caption('Готово', 2200);
  await d.save('backlog-planning-params');
});
