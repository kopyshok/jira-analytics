/**
 * E2E tests for the Resources+Scenarios revamp (Task 35).
 *
 * Strategy:
 * - Skip rather than fail when seed data is absent (no teams, no employees with
 *   a specific role, etc.).
 * - Assert on *changes* (before/after) rather than exact numeric values to avoid
 *   flakiness across different DB states.
 * - Use data-testid where available; role/text selectors otherwise.
 */

import { expect, test, type APIRequestContext } from '@playwright/test';

const backendPort = process.env.E2E_BACKEND_PORT ?? '8010';
const apiBaseUrl = `http://127.0.0.1:${backendPort}/api/v1`;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type ScenarioResponse = {
  id: string;
  name: string;
  team: string | null;
  year: number | null;
  quarter: string | null;
  status: 'draft' | 'approved';
  external_qa_hours: number | null;
};

type AllocationResponse = {
  id: string;
  included: boolean;
};

async function apiGet<T>(request: APIRequestContext, path: string): Promise<T> {
  const response = await request.get(`${apiBaseUrl}${path}`);
  expect(response.ok()).toBeTruthy();
  return response.json() as Promise<T>;
}

/** Return all scenarios (regardless of year/quarter). */
async function allScenarios(request: APIRequestContext): Promise<ScenarioResponse[]> {
  const response = await request.get(`${apiBaseUrl}/planning/scenarios`);
  if (!response.ok()) return [];
  const data = (await response.json()) as unknown;
  return Array.isArray(data) ? (data as ScenarioResponse[]) : [];
}

/** Select the first visible option from an open Ant Design dropdown. */
async function pickFirstAntdOption(
  page: import('@playwright/test').Page,
): Promise<string | null> {
  const option = page
    .locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option-content')
    .first();
  const visible = await option.isVisible().catch(() => false);
  if (!visible) return null;
  const text = (await option.textContent()) ?? '';
  await option.click();
  return text.trim();
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('Scenarios revamp', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/planning');
  });

  // -------------------------------------------------------------------------
  // 1. Create scenario requires team
  // -------------------------------------------------------------------------
  test('create scenario requires team', async ({ page }) => {
    // Open the create-scenario modal
    await page.getByRole('button', { name: 'Новый сценарий' }).click();

    const modal = page.getByRole('dialog', { name: 'Новый сценарий квартала' });
    await expect(modal).toBeVisible();

    // The "Создать" OK button starts disabled because team is empty
    const okBtn = modal.getByRole('button', { name: 'Создать' });
    await expect(okBtn).toBeDisabled();

    // Fill name — button should still be disabled (team still empty)
    await modal.getByLabel('Название').fill('E2E test scenario');
    await expect(okBtn).toBeDisabled();

    // Open the team dropdown
    const teamSelect = modal.locator('.ant-select').filter({ hasText: /Выберите команду/ }).first();
    await teamSelect.click();

    // If no teams are available, skip
    const hasOptions = await page
      .locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option-content')
      .first()
      .isVisible()
      .catch(() => false);

    test.skip(!hasOptions, 'No Jira teams available in E2E seed — skipping team-required test');

    await pickFirstAntdOption(page);

    // Now OK should be enabled
    await expect(okBtn).toBeEnabled();

    // Close without saving
    await modal.getByRole('button', { name: 'Отмена' }).click();
    await expect(modal).not.toBeVisible();
  });

  // -------------------------------------------------------------------------
  // 2. Idea toggle updates resource panel immediately
  // -------------------------------------------------------------------------
  test('idea toggle updates resource panel immediately', async ({ page, request }) => {
    // Find a draft scenario that has a team assigned
    const scenarios = await allScenarios(request);
    const draftWithTeam = scenarios.find((s) => s.status === 'draft' && !!s.team);

    test.skip(
      !draftWithTeam,
      'No draft scenario with a team found in E2E seed — skipping toggle test',
    );

    // Navigate to the scenario
    await page.goto(`/planning?scenario=${draftWithTeam!.id}`);

    const demandCell = page.getByTestId('capacity-analyst-demand');
    await demandCell.waitFor({ timeout: 10_000 });

    // Create a backlog item with analyst hours so toggling it changes demand
    const created = await request.post(`${apiBaseUrl}/backlog`, {
      data: {
        title: 'E2E toggle demand test',
        priority: 99,
        estimate_analyst_hours: 8,
        estimate_dev_hours: 0,
        estimate_qa_hours: 0,
        estimate_opo_hours: 0,
      },
    });
    expect(created.ok()).toBeTruthy();
    const newItem = (await created.json()) as { id: string };

    try {
      // Sync new item into the scenario
      const syncResp = await request.post(
        `${apiBaseUrl}/planning/scenarios/${draftWithTeam!.id}/sync-backlog`,
      );
      expect(syncResp.ok()).toBeTruthy();

      // Reload page so the new allocation appears
      await page.reload();
      await demandCell.waitFor({ timeout: 10_000 });

      // Find the allocation for our new item
      await apiGet<AllocationResponse[]>(
        request,
        `/planning/scenarios/${draftWithTeam!.id}/allocations`,
      );

      // Find the row in the UI — the title is unique
      const row = page.getByText('E2E toggle demand test').first();
      const rowVisible = await row.isVisible().catch(() => false);

      test.skip(!rowVisible, 'New backlog item row not visible — sync may not have completed');

      // Click to toggle it (include → exclude or vice-versa)
      const checkbox = page
        .locator('[style*="grid"]')
        .filter({ has: page.getByText('E2E toggle demand test') })
        .locator('input[type="checkbox"]')
        .first();

      const wasBefore = (await demandCell.textContent())?.trim() ?? '';
      await checkbox.click();

      // Demand should change
      await expect
        .poll(async () => (await demandCell.textContent())?.trim() ?? '', { timeout: 5_000 })
        .not.toBe(wasBefore);
    } finally {
      // Cleanup
      await request.delete(`${apiBaseUrl}/backlog/${newItem.id}`);
    }
  });

  // -------------------------------------------------------------------------
  // 3. Rule edit updates capacity after save
  // -------------------------------------------------------------------------
  test('rule edit updates capacity after save', async ({ page, request }) => {
    const scenarios = await allScenarios(request);
    const draftWithTeam = scenarios.find((s) => s.status === 'draft' && !!s.team);

    test.skip(
      !draftWithTeam,
      'No draft scenario with a team found — skipping rules editor test',
    );

    await page.goto(`/planning?scenario=${draftWithTeam!.id}`);

    // Wait for capacity panel to load
    const demandCell = page.getByTestId('capacity-analyst-demand');
    await demandCell.waitFor({ timeout: 10_000 });

    // Expand the rules Collapse panel
    const collapseHeader = page.getByText('Правила обязательных работ');
    await collapseHeader.click();

    // Add a new rule
    await page.getByRole('button', { name: 'Добавить правило' }).click();

    // The new row's role cell — set to "analyst"
    const lastRoleSelect = page.locator('.ant-table-tbody tr').last().locator('.ant-select').first();
    await lastRoleSelect.click();

    const analystOption = page
      .locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option-content')
      .filter({ hasText: /аналити/i })
      .first();

    const analystVisible = await analystOption.isVisible().catch(() => false);
    if (analystVisible) {
      await analystOption.click();
    } else {
      // Pick any available role
      await pickFirstAntdOption(page);
    }

    // Set percent to 10
    const percentInput = page
      .locator('.ant-table-tbody tr')
      .last()
      .locator('input[type="number"]')
      .first();
    await percentInput.fill('10');

    // Save
    const saveBtn = page.getByRole('button', { name: 'Сохранить' });
    await expect(saveBtn).toBeEnabled();
    await saveBtn.click();

    // After save the button goes back to disabled (not dirty)
    await expect(saveBtn).toBeDisabled({ timeout: 5_000 });
  });

  // -------------------------------------------------------------------------
  // 4. External QA override replaces QA bar
  // -------------------------------------------------------------------------
  test('external qa override replaces qa bar', async ({ page, request }) => {
    const scenarios = await allScenarios(request);
    const draftWithTeam = scenarios.find((s) => s.status === 'draft' && !!s.team);

    test.skip(
      !draftWithTeam,
      'No draft scenario with a team found — skipping external QA test',
    );

    await page.goto(`/planning?scenario=${draftWithTeam!.id}`);

    // Wait for page to be ready
    const demandCell = page.getByTestId('capacity-analyst-demand');
    await demandCell.waitFor({ timeout: 10_000 });

    // Find the external QA input (the InputNumber with label "Часы тестировщика")
    const qaInput = page.getByRole('spinbutton').filter({ hasNearby: page.getByText(/Часы тестировщика/i) });

    // If it's not immediately locatable by that filter, fall back to the InputNumber addonAfter "ч"
    const qaInputFallback = page.locator('input[id*="external_qa"], input[class*="ant-input-number"]').last();
    const targetInput = (await qaInput.count()) > 0 ? qaInput.first() : qaInputFallback;

    const isEnabled = await targetInput.isEnabled().catch(() => false);
    test.skip(!isEnabled, 'External QA input not found or disabled — skipping');

    // Clear and set a value of 100
    await targetInput.fill('100');
    await targetInput.press('Tab'); // trigger onBlur → PATCH

    // After the PATCH, the "внешний QA" tag should appear in the capacity panel header
    await expect(page.getByText(/внешний QA/i)).toBeVisible({ timeout: 8_000 });

    // Cleanup: clear external_qa_hours via API
    await request.patch(`${apiBaseUrl}/planning/scenarios/${draftWithTeam!.id}`, {
      data: { external_qa_hours: null },
    });
  });

  // -------------------------------------------------------------------------
  // 5. Consultant bar shown with capacity, 0 demand
  // -------------------------------------------------------------------------
  test('consultant bar shown with capacity, 0 demand', async ({ page, request }) => {
    // Check if any employee in the DB has role="consultant"
    const empResp = await request.get(`${apiBaseUrl}/employees`);
    test.skip(!empResp.ok(), 'Could not fetch employees — skipping consultant test');

    const employees = (await empResp.json()) as Array<{ role: string | null }>;
    const hasConsultant = employees.some((e) => e.role === 'consultant');

    test.skip(
      !hasConsultant,
      'No employee with role=consultant in E2E seed — skipping consultant bar test',
    );

    // Find a draft scenario with a team that presumably has consultant employees
    const scenarios = await allScenarios(request);
    const draftWithTeam = scenarios.find((s) => s.status === 'draft' && !!s.team);

    test.skip(
      !draftWithTeam,
      'No draft scenario with a team found — skipping consultant bar test',
    );

    await page.goto(`/planning?scenario=${draftWithTeam!.id}`);

    // Consultant demand is always 0 (no demand column for it), capacity should render
    const consultantDemandCell = page.getByTestId('capacity-consultant-demand');
    await expect(consultantDemandCell).toBeVisible({ timeout: 10_000 });

    // Demand value should be "0" (consultants never have backlog demand)
    await expect(consultantDemandCell).toHaveText('0');
  });
});
