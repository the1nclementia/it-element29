import { defineConfig, devices } from '@playwright/test';

// Playwright's failure DOM dump includes password input values. Keep it disabled.
process.env.PLAYWRIGHT_NO_COPY_PROMPT = '1';

// Run only against an explicitly selected disposable acceptance environment.
if (!process.env.E2E_BASE_URL || !process.env.E2E_ADMIN_PASSWORD) {
  throw new Error(
    'Задайте E2E_BASE_URL и E2E_ADMIN_PASSWORD тестового окружения.',
  );
}

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL,
    trace: 'off',
    screenshot: 'only-on-failure',
    ...devices['Desktop Chrome'],
    launchOptions: process.env.E2E_CHROMIUM_PATH
      ? { executablePath: process.env.E2E_CHROMIUM_PATH }
      : {},
  },
});
