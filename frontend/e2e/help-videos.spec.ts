import { expect, test } from '@playwright/test';
import { loginAs } from './helpers';

// Сидовый e2e-пользователь не привязан к команде, поэтому панель «Первые шаги»
// не показывает шаг «Отсутствия» с кнопкой «Видео» — проверяем показ ролика
// через справку раздела Capacity, где ролик доступен всегда.
test('help drawer: video card opens the video in a modal', async ({ page }) => {
  await loginAs(page);

  // На чистой e2e.db у сидового пользователя может показаться модалка
  // «Что нового» при первом входе — закрыть, если она есть.
  const whatsNewOk = page.getByRole('button', { name: 'Понятно' });
  try {
    await whatsNewOk.waitFor({ state: 'visible', timeout: 3000 });
    await whatsNewOk.click();
  } catch {
    // модалки нет — ничего закрывать не нужно
  }

  await page.goto('/capacity');
  await page.locator('button:has(.anticon-question-circle)').click();
  // Есть непрочитанные заметки «Что нового» — по умолчанию открывается их вкладка.
  await page.getByRole('tab', { name: 'Справка' }).click();

  const videoCard = page.getByRole('button', { name: 'Смотреть видео: Как внести отпуск' });
  await expect(videoCard).toBeVisible();
  await videoCard.click();

  const video = page.locator('.ant-modal video');
  await expect(video).toBeVisible();
  await expect(video).toHaveAttribute('src', /absence-add\.webm$/);
});
