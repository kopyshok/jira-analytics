import { test } from '@playwright/test';
import { expectNoBrowserErrors, expectVisible, loginAs, trackBrowserErrors } from './helpers';

test('first steps panel opens and runs the dashboard tour', async ({ page }) => {
  await loginAs(page);
  // Трекер стартует после входа: страница логина сама по себе шлёт ожидаемый
  // 401 (профиль ещё не поднят) — это не имеет отношения к тесту.
  const browserErrors = trackBrowserErrors(page);

  // На чистой e2e.db у сидового пользователя ещё нет last_seen_release_version,
  // поэтому при первом входе может появиться модалка «Что нового» — закрыть,
  // если она есть, чтобы не перекрывала кнопку «Первые шаги».
  const whatsNewOk = page.getByRole('button', { name: 'Понятно' });
  try {
    await whatsNewOk.waitFor({ state: 'visible', timeout: 3000 });
    await whatsNewOk.click();
  } catch {
    // модалки нет — ничего закрывать не нужно
  }

  await page.getByTestId('onboarding-button').click();
  await expectVisible(page.getByText('Знакомство с сервисом', { exact: true }));

  await page.getByTestId('tour-start-dashboard').click();
  await expectVisible(page.locator('.ant-tour').getByText('Проекты квартала', { exact: true }));

  await expectNoBrowserErrors(browserErrors);
});
