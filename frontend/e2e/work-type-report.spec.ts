/**
 * E2E smoke test for the Work-Type Thematic Report page.
 *
 * Navigation strategy: after loginAs (lands on /, SPA state intact), use the
 * AntD sidebar menu item to navigate via React Router (client-side, no reload).
 * This preserves the AuthProvider's in-memory user state.
 *
 * Flow:
 *   1. Login → click sidebar "Тематический отчёт" → wait for page to render
 *   2. Select E2E work type from Radio.Group in Toolbar (if visible)
 *   3. Wait for report to build and KPI row to appear
 *   4. Open "Словарь тем" drawer → assert drawer opens
 *   5. Close drawer → click "PDF для руководства" → new tab opens at /print URL
 *      → assert title block visible in print view
 *
 * NOTE: Candidate acceptance (original spec step 4) is SKIPPED because no LLM
 * provider is configured in the E2E environment, so the classifier produces zero
 * candidates.  Candidate acceptance is covered by unit tests in the backend.
 *
 * Seed data: seed_e2e.py plants MandatoryWorkType "e2e_support_consult"
 * (id: 00000000-0000-0000-0000-000000000010) with label "E2E Сопровождение"
 * + Category + 5 Issues + Worklogs in 2026-Q2.
 */

import { expect, test } from '@playwright/test';
import { loginAs } from './helpers';

// Label of the E2E work type seeded in seed_e2e.py
const E2E_WORK_TYPE_LABEL = 'E2E Сопровождение';

// Allow extra time for auth + report build on cold start.
test.setTimeout(90_000);

test('work-type report: report loads → KPI visible → dictionary drawer → PDF tab', async ({
  page,
  context,
}) => {
  // ── 0. Login (lands on / via SPA redirect after successful auth) ──────────
  await loginAs(page);

  // Wait for dashboard to render (confirms AppLayout and sidebar are mounted).
  await expect(page.locator('.ant-layout-sider')).toBeVisible({ timeout: 15_000 });

  // ── 1. Click "Тематический отчёт" in the sidebar (SPA navigation) ─────────
  //   AntD Menu renders items; the span inside has the label text.
  await page.locator('.ant-menu-item').filter({ hasText: 'Тематический отчёт' }).click();

  // Confirm URL changed to the work-type-report route.
  await page.waitForURL('**/analytics/work-type-report**', { timeout: 10_000 });

  // ── 2. Wait for page content: either EmptyState button or Toolbar ─────────
  //   isEmpty = themes.length === 0 && !report
  //   → EmptyState while report is loading or if no data
  //   → Toolbar when report is loaded
  const emptyBuildBtn = page.getByRole('button', { name: 'Построить первый отчёт' });
  const dictionaryBtn = page.getByRole('button', { name: 'Словарь тем' });

  // Wait for one of them to appear.
  await expect(emptyBuildBtn.or(dictionaryBtn)).toBeVisible({ timeout: 30_000 });

  // ── 3. If EmptyState, click "Построить первый отчёт" ─────────────────────
  if (await emptyBuildBtn.isVisible().catch(() => false)) {
    await emptyBuildBtn.click();
    // Wait for toolbar to appear after build completes.
    await expect(dictionaryBtn).toBeVisible({ timeout: 30_000 });
  }

  // ── 4. Select E2E work type from the Radio.Group if available ────────────
  //   The Toolbar renders work type buttons. If our E2E type is present,
  //   click it to trigger the report for our seeded data.
  const e2eRadio = page.getByRole('radio', { name: E2E_WORK_TYPE_LABEL });
  if (await e2eRadio.isVisible({ timeout: 3_000 }).catch(() => false)) {
    await e2eRadio.click();
    // Wait for the new report to load.
    await expect(dictionaryBtn).toBeVisible({ timeout: 30_000 });
  }

  // ── 5. Verify KPI row labels are visible ──────────────────────────────────
  //   KpiRow renders "Часов", "Задач", "Сотрудников" as card labels.
  //   "Задач" is scoped to .ant-card to avoid collision with sidebar items
  //   "Целевые задачи" / "Категории задач" that also contain "задач".
  await expect(page.locator('text=Часов').first()).toBeVisible({ timeout: 30_000 });
  await expect(
    page.locator('.ant-card').filter({ hasText: 'Задач' }).first(),
  ).toBeVisible();
  await expect(page.locator('text=Сотрудников').first()).toBeVisible();

  // ── 6. Open "Словарь тем" drawer ─────────────────────────────────────────
  await dictionaryBtn.click();
  await expect(page.locator('.ant-drawer-content-wrapper')).toBeVisible({ timeout: 5_000 });

  // Close the drawer.
  // AntD Drawer close button uses aria-label="Закрыть" (Russian locale).
  await page.locator('.ant-drawer-open').getByRole('button', { name: 'Закрыть' }).click();
  await expect(page.locator('.ant-drawer-open')).toHaveCount(0, { timeout: 5_000 });

  // ── 7. Click "PDF для руководства" → new tab opens ───────────────────────
  const [printPage] = await Promise.all([
    context.waitForEvent('page'),
    page.getByRole('button', { name: 'PDF для руководства' }).click(),
  ]);

  await printPage.waitForLoadState('domcontentloaded');

  // Assert URL contains the print route
  expect(printPage.url()).toContain('/analytics/work-type-report/print');
  expect(printPage.url()).toContain('work_type_id=');

  // PrintView renders "Тематический отчёт" as a small uppercase label.
  // Auth cookie is shared across the browser context, so the print page
  // receives the same auth as the main page.
  await expect(printPage.getByText('Тематический отчёт', { exact: true })).toBeVisible({
    timeout: 30_000,
  });

  await printPage.close();
});
