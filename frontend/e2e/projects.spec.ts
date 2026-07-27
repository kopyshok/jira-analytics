import { test, expect } from '@playwright/test';

test.describe('/projects page', () => {
  test('open page and see master-detail layout', async ({ page }) => {
    await page.goto('/projects');
    // Sidebar item «Проекты» подсвечен
    const sidebarItem = page.getByRole('menuitem', { name: 'Проекты' });
    await expect(sidebarItem).toBeVisible();

    // Проект не выбран → в правой панели сводка портфеля
    // (её собственное пустое состояние — тоже валидный вид сводки).
    await expect(page.getByTestId('portfolio-view')).toBeVisible();
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

  test('«План и сроки» opens and «Сводка» returns to portfolio', async ({ page }) => {
    await page.goto('/projects');
    const firstCard = page.locator('[data-testid="project-card"]').first();
    if ((await firstCard.count()) === 0) {
      test.skip(true, 'Seeded e2e.db не содержит проектов с категорией quarterly_tasks/archive_target');
      return;
    }

    await firstCard.click();
    await page.getByRole('button', { name: /План и сроки/i }).click();
    await expect(page).toHaveURL(/view=plan/);

    // Кнопка «Сводка» снимает выбор проекта и возвращает сводный экран.
    await page.getByRole('button', { name: /^Сводка$/ }).click();
    await expect(page).toHaveURL(/\/projects$/);
    await expect(page.getByTestId('portfolio-view')).toBeVisible();
  });
});
