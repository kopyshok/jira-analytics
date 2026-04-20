import { expect, test } from '@playwright/test';

// ---------------------------------------------------------------------------
// Helpers (local to this spec)
// ---------------------------------------------------------------------------

async function clickPrimaryInModal(page: import('@playwright/test').Page) {
  await page.locator('.ant-modal').last().locator('.ant-btn-primary').click();
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test('Распределение and Правила tabs absent, Роли tab present', async ({ page }) => {
  await page.goto('/capacity');

  await expect(page.getByRole('tab', { name: 'Распределение' })).toHaveCount(0);
  await expect(page.getByRole('tab', { name: 'Правила' })).toHaveCount(0);
  await expect(page.getByRole('tab', { name: 'Роли' })).toBeVisible();
});

test('Роли tab — can add and delete a role', async ({ page, request }) => {
  await page.goto('/capacity');
  await page.getByRole('tab', { name: 'Роли' }).click();

  await page.getByRole('button', { name: /Добавить роль/i }).click();

  const modal = page.getByRole('dialog', { name: 'Новая роль' });
  await expect(modal).toBeVisible();

  // Form.Item labels in RolesTab: label="Code" (English) and label="Название"
  await modal.getByLabel('Code').fill('e2etest');
  await modal.getByLabel('Название').fill('E2E Test Role');

  // Submit via modal OK button
  await clickPrimaryInModal(page);

  // The new role should appear in the table
  await expect(page.getByRole('cell', { name: 'e2etest' })).toBeVisible({ timeout: 5000 });
  await expect(page.getByText('E2E Test Role')).toBeVisible();

  // Cleanup: delete the newly created role
  const newRoleRow = page.locator('tr').filter({ hasText: 'e2etest' });
  // Delete button is a red Tag with DeleteOutlined icon inside a Popconfirm
  await newRoleRow.locator('.ant-tag[style*="cursor: pointer"]').click();

  // Confirm the popconfirm (okText="Удалить")
  await page.locator('.ant-popconfirm').last().getByRole('button', { name: 'Удалить' }).click();

  await expect(page.getByRole('cell', { name: 'e2etest' })).toHaveCount(0, { timeout: 5000 });

  // Also verify via API that the role is gone
  const backendPort = process.env.E2E_BACKEND_PORT ?? '8010';
  const roles = await (await request.get(`http://127.0.0.1:${backendPort}/api/v1/roles`)).json() as { code: string }[];
  expect(roles.some((r) => r.code === 'e2etest')).toBeFalsy();
});

test('Пересчитать часы button — visible and enabled when one team selected', async ({ page }) => {
  await page.goto('/capacity');
  // «Команда» tab is the default

  // The button is always rendered but disabled when selectedTeams.length !== 1.
  // In E2E the TeamFilterBar sources teams from /sync/jira-teams (requires Jira
  // credentials not available in E2E) — so the dropdown may return no options.
  // We detect this and skip rather than fail.

  const recalcBtn = page.getByRole('button', { name: 'Пересчитать часы' });
  await expect(recalcBtn).toBeVisible();

  // Open the team filter dropdown (TeamFilterBar in page header)
  await page.locator('[placeholder="Фильтр по команде (применяется ко всем вкладкам)"]').click();
  const dropdown = page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden)');
  const optionCount = await dropdown.locator('.ant-select-item-option').count();

  if (optionCount === 0) {
    // No teams available in E2E (no Jira credentials) — button remains disabled, skip
    test.skip(true, 'No teams in E2E dropdown — Пересчитать часы cannot be tested without a team');
    return;
  }

  // Pick the first available team
  await dropdown.locator('.ant-select-item-option').first().click();

  // Now exactly one team is selected → button should be enabled
  await expect(recalcBtn).toBeEnabled({ timeout: 3000 });

  // Click and expect the success notification
  await recalcBtn.click();
  await expect(page.getByText('Часы пересчитаны')).toBeVisible({ timeout: 10000 });
});
