import { test, expect } from '@playwright/test';

test.describe('/projects page', () => {
  test('open page and see master-detail layout', async ({ page }) => {
    await page.goto('/projects');
    // Sidebar item «Проекты» подсвечен
    const sidebarItem = page.getByRole('menuitem', { name: 'Проекты' });
    await expect(sidebarItem).toBeVisible();

    // Empty state в правой панели когда не выбран проект
    await expect(page.getByText(/Выберите проект/i)).toBeVisible();
  });

  test('search filter is interactive', async ({ page }) => {
    await page.goto('/projects');
    const search = page.getByPlaceholder(/Поиск/i);
    await search.fill('test');
    await search.press('Enter');
    // search не должен крашить страницу — мин. проверка
    await expect(search).toHaveValue('test');
  });

  test('toggle Анализ ↔ Презентация changes URL', async ({ page }) => {
    // Если в seeded e2e.db есть проект — кликни первую карточку. Иначе skip.
    await page.goto('/projects');
    const firstCard = page.locator('[data-testid="project-card"]').first();
    const count = await firstCard.count();
    if (count === 0) {
      test.skip(true, 'Seeded e2e.db не содержит проектов с категорией quarterly_tasks/archive_target');
      return;
    }

    await firstCard.click();
    // URL обновился на /projects/:key
    await expect(page).toHaveURL(/\/projects\/[A-Z]+-\d+/);

    // Toggle на Презентация
    await page.getByRole('button', { name: /Презентация/i }).click();
    await expect(page).toHaveURL(/view=presentation/);

    // Toggle обратно на Анализ
    await page.getByRole('button', { name: /Анализ/i }).click();
    await expect(page).not.toHaveURL(/view=presentation/);
  });
});
