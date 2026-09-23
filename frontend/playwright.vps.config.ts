import { defineConfig } from '@playwright/test'

/**
 * Playwright config for tests against the production VPS.
 * No webServer block — tests hit http://187.124.64.227:3003 directly.
 */
export default defineConfig({
  testDir: './e2e',
  testMatch: /vps-.*\.spec\.ts$/,
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: 'list',
  timeout: 45000,
  use: {
    baseURL: 'https://dashboard-ia-ucompensar.187.124.64.227.nip.io',
    trace: 'on',
    screenshot: 'on',
    video: 'retain-on-failure',
    ignoreHTTPSErrors: false,
    // Fuerza la resolución DNS del subdominio nip.io directo a la IP del VPS.
    // Útil cuando el resolver local no resuelve subdominios nip.io.
    launchOptions: {
      args: [
        '--host-resolver-rules=MAP dashboard-ia-ucompensar.187.124.64.227.nip.io 187.124.64.227',
      ],
    },
  },
})
