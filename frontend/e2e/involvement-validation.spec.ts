import { expect, test } from '@playwright/test';
import { loginAs } from './helpers';

const backendPort = process.env.E2E_BACKEND_PORT ?? '8010';
const apiBaseUrl = `http://127.0.0.1:${backendPort}/api/v1`;

// Регрессия: поле «Вовлечённость, %» молча подменяло 0 на 1, и запись
// сохранялась с 1%. Теперь 0 остаётся в поле, под ним — ошибка, «Добавить» недоступна.
test('личная вовлечённость 0% не подменяется и не сохраняется', async ({ page }) => {
  await loginAs(page);
  // Запросы — из страницы: кука входа защищённая, запросы самого теста её не несут.
  const api = (method: string, path: string, body?: unknown) =>
    page.evaluate(
      async ([url, m, data]) => {
        const r = await fetch(url, {
          method: m,
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: data === undefined ? undefined : JSON.stringify(data),
        });
        return { ok: r.ok, text: await r.text() };
      },
      [`${apiBaseUrl}${path}`, method, body] as const,
    );
  const created = await api('POST', '/planning/scenarios', {
    name: 'E2E involvement 0%', year: 2026, quarter: 2, team: 'E2E Squad',
  });
  expect(created.ok, created.text).toBeTruthy();
  const { id } = JSON.parse(created.text) as { id: string };

  try {
    await page.goto(`/planning?scenario=${id}`);
    const whatsNewOk = page.getByRole('button', { name: 'Понятно' });
    // При первом входе может всплыть «Что нового» — закрыть, чтобы не перекрывало кнопки.
    await whatsNewOk.waitFor({ state: 'visible', timeout: 5000 }).then(() => whatsNewOk.click(), () => {});

    await page.getByRole('button', { name: 'Вовлечённость' }).click();
    await page.locator('.ant-drawer').getByRole('button', { name: 'Добавить' }).last().click();
    const modal = page.getByRole('dialog', { name: 'Добавить сотрудника' });
    await modal.locator('#personal-setting-employee').click();
    await page.locator('.ant-select-dropdown:visible').getByText('E2E Analyst').click();

    const input = modal.locator('#personal-setting-involvement');
    await input.fill('0');
    await input.press('Tab');
    await expect(input).toHaveValue('0');
    await expect(modal.getByText('Вовлечённость — от 1 до 100%')).toBeVisible();
    await expect(modal.getByRole('button', { name: 'Добавить' })).toBeDisabled();

    await input.fill('50');
    await expect(modal.getByText('Вовлечённость — от 1 до 100%')).toBeHidden();
    await expect(modal.getByRole('button', { name: 'Добавить' })).toBeEnabled();
  } finally {
    await api('DELETE', `/planning/scenarios/${id}`);
  }
});
