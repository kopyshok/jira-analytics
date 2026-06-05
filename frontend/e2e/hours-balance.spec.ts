import { expect, test } from '@playwright/test';
import { expectNoBrowserErrors, expectVisible, trackBrowserErrors } from './helpers';

test.describe('Виджет «Баланс часов команды»', () => {
  test('виджет отображается на дашборде', async ({ page }) => {
    const browserErrors = trackBrowserErrors(page);

    await page.goto('/');
    await expectVisible(
      page.getByText('Баланс часов команды', { exact: true }).first(),
    );

    await expectNoBrowserErrors(browserErrors);
  });

  test('клик по карточке открывает модалку, Escape закрывает', async ({ page }) => {
    const browserErrors = trackBrowserErrors(page);

    await page.goto('/');

    // Дождаться окончания загрузки виджета
    await page.waitForTimeout(3000);

    // Карточки сотрудников появляются только при наличии данных
    const card = page
      .locator('[role="button"]')
      .filter({ hasText: /Переработок:/ })
      .first();

    const cardCount = await card.count();
    if (cardCount === 0) {
      test.skip();
      return;
    }

    await card.click();

    // Модалка с заголовком «Баланс часов — <имя>»
    await expect(page.getByText(/Баланс часов —/)).toBeVisible({ timeout: 5000 });

    // Escape закрывает модалку
    await page.keyboard.press('Escape');
    await expect(page.getByText(/Баланс часов —/)).not.toBeVisible({ timeout: 3000 });

    await expectNoBrowserErrors(browserErrors);
  });
});
