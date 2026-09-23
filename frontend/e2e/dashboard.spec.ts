import { test, expect, type Page } from '@playwright/test'

/**
 * Sets auth tokens via the browser so the middleware cookie check passes.
 * Call this before navigating to any protected route.
 */
async function loginViaAPI(page: Page): Promise<void> {
  const API_URL = 'http://localhost:8001'

  const res = await page.request.post(`${API_URL}/api/v1/auth/login`, {
    data: {
      email: process.env.E2E_TEST_EMAIL || 'test@ferreteria.com',
      password: process.env.E2E_TEST_PASSWORD || 'Test12345!',
    },
  })

  if (!res.ok()) {
    throw new Error(
      `Backend no disponible para login e2e (status ${res.status()}). ` +
      'Asegúrate de que el backend esté corriendo antes de ejecutar los tests e2e.'
    )
  }

  const tokens = await res.json()
  const accessToken = tokens.access_token as string

  await page.context().addCookies([
    {
      name: 'access_token',
      value: accessToken,
      domain: 'localhost',
      path: '/',
    },
  ])

  // Also set localStorage tokens for client-side API calls
  await page.addInitScript((token: string) => {
    localStorage.setItem('access_token', token)
  }, accessToken)
}

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaAPI(page)
  })

  test('page loads after login', async ({ page }) => {
    await page.goto('/')

    // The dashboard has an h1 with "Dashboard" text
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
  })

  test('shows quick stats cards', async ({ page }) => {
    await page.goto('/')

    await expect(page.getByText('Registros totales')).toBeVisible()
    await expect(page.getByRole('paragraph').filter({ hasText: 'Tablas de datos' })).toBeVisible()
    await expect(page.getByText('Archivos procesados')).toBeVisible()
  })

  test('has CTA button to open ChatBot', async ({ page }) => {
    await page.goto('/')

    await expect(
      page.getByRole('link', { name: /Abrir ChatBot/ })
    ).toBeVisible()
  })
})

test.describe('Navigation Sidebar', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaAPI(page)
  })

  test('sidebar contains expected navigation links', async ({ page }) => {
    await page.goto('/')

    // The sidebar renders these nav items (visible on desktop viewport)
    await expect(page.getByRole('link', { name: 'Resumen' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Mis Datos' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Tableros' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Análisis IA' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Chat IA' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Configuración' })).toBeVisible()
  })

  test('clicking Chat IA navigates to /chat', async ({ page }) => {
    await page.goto('/')

    await page.getByRole('link', { name: 'Chat IA' }).click()
    await page.waitForURL('**/chat')

    expect(page.url()).toContain('/chat')
  })

  test('clicking Análisis IA navigates to /analyze', async ({ page }) => {
    await page.goto('/')

    await page.getByRole('link', { name: 'Análisis IA' }).click()
    await page.waitForURL('**/analyze')

    expect(page.url()).toContain('/analyze')
  })

  test('clicking Configuración navigates to /settings', async ({ page }) => {
    await page.goto('/')

    await page.getByRole('link', { name: 'Configuración' }).click()
    await page.waitForURL('**/settings')

    expect(page.url()).toContain('/settings')
  })
})
