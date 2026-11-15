import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  reporter: 'list',
  use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 },
    trace: 'retain-on-failure' },
});
