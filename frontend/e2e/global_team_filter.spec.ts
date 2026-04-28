import { test, expect } from '@playwright/test';
import { loginAs } from './helpers';

test('global team filter pill appears in header', async ({ page }) => {
  await loginAs(page);
  const pill = page.locator('button:has(.anticon-team)').first();
  await expect(pill).toBeVisible();
});

test('global team filter persists across reload', async ({ page }) => {
  await loginAs(page);
  const pill = page.locator('button:has(.anticon-team)').first();
  await pill.click();

  // Wait for the "Применить" button inside the popover to confirm it's open.
  // (AntD 6 popover inner may use CSS transitions so we key off the button.)
  const applyBtn = page.getByRole('button', { name: 'Применить' });
  await expect(applyBtn).toBeVisible();

  // Open the multi-select dropdown — locate the combobox inside the popover
  // (scoped to the AntD floating layer so we don't hit other selects on the page)
  const selectCombobox = page.locator('[role=tooltip] [role=combobox]').first();
  await selectCombobox.click();

  // Check whether any options are available (requires Jira teams in DB)
  const firstOption = page.locator('.ant-select-item-option').first();
  const hasOptions = await firstOption
    .waitFor({ state: 'visible', timeout: 3000 })
    .then(() => true)
    .catch(() => false);

  if (!hasOptions) {
    // No teams loaded in e2e.db (requires Jira credentials). Skip persistence check.
    test.skip(true, 'seed has no Jira teams — persistence test skipped');
    return;
  }

  const optionText = (await firstOption.textContent()) ?? '';
  await firstOption.click();

  // Apply
  await applyBtn.click();

  // Pill should reflect the selection
  const trimmed = optionText.trim();
  await expect(pill).toContainText(trimmed);

  // Reload — selection should persist (saved via PUT /auth/me/teams)
  await page.reload();
  const pillAfter = page.locator('button:has(.anticon-team)').first();
  await expect(pillAfter).toBeVisible();
  await expect(pillAfter).toContainText(trimmed);
});
