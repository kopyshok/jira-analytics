import { expect, type Locator, type Page } from '@playwright/test';

export const E2E_EMAIL = 'e2e-admin@example.com';
export const E2E_PASSWORD = 'e2etest123';

export async function loginAs(page: Page, email = E2E_EMAIL, password = E2E_PASSWORD) {
  await page.goto('/login');
  await page.fill('input[type=email]', email);
  await page.fill('input[type=password]', password);
  await page.click('button[type=submit]');
  await page.waitForURL(/\/(?!login)/);
}

export type BrowserErrorTracker = {
  errors: string[];
};

export function trackBrowserErrors(page: Page): BrowserErrorTracker {
  const tracker: BrowserErrorTracker = { errors: [] };

  page.on('console', (message) => {
    if (message.type() === 'error') {
      tracker.errors.push(message.text());
    }
  });

  page.on('pageerror', (error) => {
    tracker.errors.push(error.message);
  });

  return tracker;
}

export async function expectVisible(locator: Locator) {
  await expect(locator).toBeVisible();
}

export async function expectNoBrowserErrors(tracker: BrowserErrorTracker) {
  await expect
    .poll(() => tracker.errors, { timeout: 300 })
    .toEqual([]);
}
