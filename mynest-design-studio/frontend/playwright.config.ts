import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for the furniture-missing evidence investigation ONLY.
 * It does not start or modify the app; it targets the already-running dev servers
 * (frontend :5173, backend :8001). No production code/config is touched.
 */
export default defineConfig({
  testDir: './e2e',
  outputDir: './tests/artifacts/playwright-output',
  reporter: [['list'], ['html', { outputFolder: './tests/artifacts/playwright-report', open: 'never' }]],
  use: {
    baseURL: process.env.FRONTEND_URL || 'http://localhost:5173',
    screenshot: 'only-on-failure',
    trace: 'off',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
