import { expect, test } from '@playwright/test';
import { expectNoBrowserErrors, loginAs, trackBrowserErrors } from './helpers';

const PAGES: Array<{ path: string; name: string }> = [
  { path: '/', name: 'dashboard' },
  { path: '/projects', name: 'projects' },
  { path: '/analytics', name: 'analytics' },
  { path: '/analytics/work-type-report', name: 'work-type-report' },
  { path: '/executive', name: 'executive' },
  { path: '/capacity', name: 'capacity' },
  { path: '/backlog', name: 'backlog' },
  { path: '/planning', name: 'planning' },
  { path: '/resource-planning', name: 'resource-planning' },
  { path: '/sync', name: 'sync' },
  { path: '/categories', name: 'categories' },
  { path: '/feedback', name: 'feedback' },
  { path: '/settings', name: 'settings' },
];

for (const mode of ['aurora-dark', 'aurora-light'] as const) {
  test.describe(`Aurora ${mode}`, () => {
    test(`renders all routes without console errors in ${mode}`, async ({ page }) => {
      const errors = trackBrowserErrors(page);
      await page.addInitScript((m) => {
        window.localStorage.setItem('app_theme', m);
      }, mode);

      await loginAs(page);

      // Confirm <html data-theme="aurora"> applied
      await expect(page.locator('html[data-theme="aurora"]')).toBeAttached();

      for (const p of PAGES) {
        await page.goto(p.path);
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {
          // Some pages stream SSE; networkidle may never settle — that's OK.
        });
        // Visual sanity: html still in aurora mode
        const themeAttr = await page.locator('html').getAttribute('data-theme');
        expect(themeAttr, `at ${p.name}`).toBe('aurora');
      }

      await expectNoBrowserErrors(errors);
    });
  });
}
