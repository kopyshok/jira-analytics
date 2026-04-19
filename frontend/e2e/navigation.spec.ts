import { expect, test } from '@playwright/test';
import { expectNoBrowserErrors, expectVisible, trackBrowserErrors } from './helpers';

test('main product routes render without browser errors', async ({ page }) => {
  const browserErrors = trackBrowserErrors(page);

  await page.goto('/');
  await expectVisible(page.getByText('Всего часов'));
  await expectVisible(page.getByText('Статус синхронизации'));

  await page.getByRole('menuitem', { name: 'Аналитика' }).click();
  await expect(page).toHaveURL(/\/analytics$/);
  await expectVisible(page.getByRole('tab', { name: 'По сотрудникам' }));
  await expectVisible(page.getByRole('tab', { name: 'Переключения контекста' }));

  await page.getByRole('menuitem', { name: 'Синхронизация' }).click();
  await expect(page).toHaveURL(/\/sync$/);
  await expectVisible(page.getByRole('button', { name: 'Проверить подключение' }));
  await expectVisible(page.getByRole('button', { name: 'Полная синхронизация' }));

  await page.getByRole('menuitem', { name: 'Скоуп' }).click();
  await expect(page).toHaveURL(/\/scope$/);
  await expectVisible(page.getByRole('tab', { name: 'Проекты' }));
  await expectVisible(page.getByPlaceholder('Ключ проекта (напр. PROJ)'));

  await page.getByRole('menuitem', { name: 'Ресурсы' }).click();
  await expect(page).toHaveURL(/\/capacity$/);
  await expectVisible(page.getByRole('tab', { name: 'Команда' }));
  await expectVisible(page.getByRole('tab', { name: 'Отсутствия' }));

  await page.getByRole('menuitem', { name: 'Бэклог' }).click();
  await expect(page).toHaveURL(/\/backlog$/);
  await expectVisible(page.getByRole('button', { name: 'Добавить' }));
  await expectVisible(page.getByRole('columnheader', { name: 'Название' }));

  await page.getByRole('menuitem', { name: 'Планирование' }).click();
  await expect(page).toHaveURL(/\/planning$/);
  await expectVisible(page.getByRole('button', { name: 'Сгенерировать сценарий' }));
  await expectVisible(page.getByText('Сценарии'));

  await expectNoBrowserErrors(browserErrors);
});
