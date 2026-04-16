import { expect, test, type Locator, type Page } from '@playwright/test';

type ConsoleTracker = {
  errors: string[];
};

function trackConsoleErrors(page: Page): ConsoleTracker {
  const tracker: ConsoleTracker = { errors: [] };

  page.on('console', (message) => {
    if (message.type() === 'error') {
      tracker.errors.push(message.text());
    }
  });

  page.on('pageerror', (error) => {
    tracker.errors.push(error.message);
  });

  return tracker;
}

async function expectVisible(locator: Locator) {
  await expect(locator).toBeVisible();
}

test('main product routes render without browser errors', async ({ page }) => {
  const consoleTracker = trackConsoleErrors(page);

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

  await page.getByRole('menuitem', { name: 'Ёмкость' }).click();
  await expect(page).toHaveURL(/\/capacity$/);
  await expectVisible(page.getByRole('tab', { name: 'Команда' }));
  await expectVisible(page.getByRole('tab', { name: 'Отпуска' }));

  await page.getByRole('menuitem', { name: 'Бэклог' }).click();
  await expect(page).toHaveURL(/\/backlog$/);
  await expectVisible(page.getByRole('button', { name: 'Добавить' }));
  await expectVisible(page.getByRole('columnheader', { name: 'Название' }));

  await page.getByRole('menuitem', { name: 'Планирование' }).click();
  await expect(page).toHaveURL(/\/planning$/);
  await expectVisible(page.getByRole('button', { name: 'Сгенерировать сценарий' }));
  await expectVisible(page.getByText('Сценарии'));

  await page.waitForTimeout(300);
  expect(consoleTracker.errors).toEqual([]);
});
