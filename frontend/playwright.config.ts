import { defineConfig, devices } from '@playwright/test'

const VPS_URL = 'https://dashboard-ia-ucompensar.187.124.64.227.nip.io'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: 'list',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? VPS_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    ignoreHTTPSErrors: false,
  },
  projects: [
    {
      name: 'mobile-iphone-se',
      use: { ...devices['iPhone SE'] },
    },
    {
      name: 'desktop',
      use: { viewport: { width: 1280, height: 800 } },
    },
  ],
})
