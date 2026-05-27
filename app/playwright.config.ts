import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/browser',
  fullyParallel: false,
  reporter: 'line',
  use: {
    baseURL: process.env.DEEPMEMO_BASE_URL ?? 'http://127.0.0.1:5173',
    trace: 'on-first-retry',
  },
});
