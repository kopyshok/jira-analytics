import { expect, test } from '@playwright/test';
import { loginAs } from './helpers';

// Регрессия: на этих страницах «?» открывал только «Что нового» — справка
// раздела не была заведена (на «Проектах» — только в карточке проекта,
// на «Отчёте по видам работ» — терялась при выключенном ИИ).
const PAGES: [string, string][] = [
  ['/feedback', 'Обратная связь'],
  ['/projects', 'Проекты'],
  ['/analytics/work-type-report', 'Отчёт по видам работ'],
];

test('справка раздела есть на «Обратной связи», «Проектах» и «Отчёте по видам работ»', async ({ page }) => {
  await loginAs(page);
  for (const [path, title] of PAGES) {
    await page.goto(path);
    // При первом входе может всплыть «Что нового» — закрыть, чтобы не перекрывало «?».
    const whatsNewOk = page.getByRole('button', { name: 'Понятно' });
    await whatsNewOk.waitFor({ state: 'visible', timeout: 3000 }).then(() => whatsNewOk.click(), () => {});

    await page.getByRole('button', { name: 'question-circle' }).first().click();
    await expect(page.locator('.ant-drawer-title'), path).toHaveText(title);
    await page.keyboard.press('Escape');
  }
});
