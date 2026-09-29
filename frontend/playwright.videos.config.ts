// Съёмка видео-инструкций на обезличенной демо-базе: `npm run videos`.
// Не входит в E2E и CI. Демо-база data/demo.db собирается заранее
// (scripts/demo_db/build_demo_db.py); перед каждым запуском берётся её свежая копия.
// Нужен Node 22.18+ (подготовка копии — скрипт на TypeScript, запускается самим node).
import { defineConfig, devices } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const pythonCmd = process.env.PYTHON_CMD ?? 'py -3.10';
const backendPort = 8012;
const frontendPort = 5176;
const backendUrl = `http://127.0.0.1:${backendPort}`;
const frontendUrl = `http://127.0.0.1:${frontendPort}`;
const viewport = { width: 1440, height: 900 };

export default defineConfig({
  testDir: './help-videos',
  testMatch: '*.video.ts',
  outputDir: './test-results/help-videos',
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'list',
  globalSetup: './help-videos/global-setup.ts',
  metadata: { backendUrl },
  use: {
    ...devices['Desktop Chrome'],
    baseURL: frontendUrl,
    storageState: fileURLToPath(new URL('../data/demo_run.auth.json', import.meta.url)),
    viewport,
    deviceScaleFactor: 1,
    video: { mode: 'on', size: viewport },
    locale: 'ru-RU',
    timezoneId: 'Europe/Moscow',
  },
  webServer: [
    {
      command:
        `node --no-warnings frontend/help-videos/prepare-db.ts && ` +
        `${pythonCmd} -m uvicorn app.main:app --host 127.0.0.1 --port ${backendPort}`,
      cwd: '..',
      url: `${backendUrl}/health`,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        DATABASE_URL: 'sqlite:///./data/demo_run.db',
        DEBUG: 'false',
        CORS_ORIGINS: frontendUrl,
        JWT_SECRET_KEY: 'help-videos-secret-not-for-production-32-chars-long',
        // Сценарии готовят данные запросами от имени демо-пользователя (page.request),
        // а по http такие запросы не передают cookie с флагом secure.
        AUTH_COOKIE_SECURE: 'false',
        // Пустые учётные данные Jira перекрывают .env: съёмка не ходит в Jira.
        JIRA_BASE_URL: 'https://jira.example.com',
        JIRA_EMAIL: '',
        JIRA_API_TOKEN: '',
      },
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${frontendPort} --strictPort`,
      url: frontendUrl,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        VITE_API_BASE_URL: `${backendUrl}/api/v1`,
      },
    },
  ],
});
