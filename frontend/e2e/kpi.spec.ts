import { test } from '@playwright/test';
import { expectNoBrowserErrors, expectVisible, loginAs, trackBrowserErrors } from './helpers';

// Раздел скрыт из меню по умолчанию (см. миграцию k09a_kpi_hidden_by_default),
// но маршрут открыт любому залогиненному — переходим по прямому URL, как и
// сам раздел это допускает (см. ревью, мелочи: раздел не был в браузерных тестах).
test('KPI page opens and renders the ledger table', async ({ page }) => {
  const browserErrors = trackBrowserErrors(page);

  await loginAs(page);
  await page.goto('/kpi');

  await expectVisible(page.getByText('KPI аналитиков'));
  await expectVisible(page.getByRole('button', { name: 'Выгрузить в Excel' }));

  // Сеяная E2E-команда состоит в KPI-отчёте по умолчанию (без фильтра —
  // все команды) — строка команды в ведомости подтверждает, что таблица
  // действительно отрисовалась, а не просто пустое состояние.
  await expectVisible(page.getByText('E2E Squad'));
  await expectVisible(page.getByRole('columnheader', { name: 'Итог' }));

  await expectNoBrowserErrors(browserErrors);
});
