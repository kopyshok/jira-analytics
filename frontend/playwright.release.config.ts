// Сводный ролик «Что нового» к релизу: `npx playwright test -c playwright.release.config.ts`.
// Та же съёмочная площадка, что у роликов справки (демо-база, серверы, вход), но свои
// сценарии глав help-videos/release/*.release.ts — общий прогон роликов справки их не снимает.
// Главы пишутся в data/release-video/clips/, склейка — help-videos/release/assemble.ts.
import { defineConfig } from '@playwright/test';
import base from './playwright.videos.config.ts';

export default defineConfig({
  ...base,
  testDir: './help-videos/release',
  testMatch: '*.release.ts',
  globalSetup: './help-videos/release/global-setup.ts',
});
