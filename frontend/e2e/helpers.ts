import { expect, type Locator, type Page } from '@playwright/test';

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
