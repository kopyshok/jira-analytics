import { defineConfig, devices } from '@playwright/test';

const pythonCmd = process.env.PYTHON_CMD ?? 'py -3.10';
const backendPort = Number(process.env.E2E_BACKEND_PORT ?? 8010);
const frontendPort = Number(process.env.E2E_FRONTEND_PORT ?? 5174);
const backendUrl = `http://127.0.0.1:${backendPort}`;
const frontendUrl = `http://127.0.0.1:${frontendPort}`;

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  globalSetup: './e2e/global-setup.ts',
  use: {
    baseURL: frontendUrl,
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: `${pythonCmd} -m uvicorn app.main:app --host 127.0.0.1 --port ${backendPort}`,
      cwd: '..',
      url: `${backendUrl}/health`,
      reuseExistingServer: false,
      timeout: 60_000,
      env: {
        DATABASE_URL: 'sqlite:///./data/e2e.db',
        DEBUG: 'false',
        CORS_ORIGINS: frontendUrl,
        JWT_SECRET_KEY: 'e2e-test-secret-not-for-production-32-chars-long-please-yes',
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
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
