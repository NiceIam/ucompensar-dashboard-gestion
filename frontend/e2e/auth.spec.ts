import { test, expect } from '@playwright/test'

test.describe('Login Page', () => {
  test('loads correctly with email, password fields and submit button', async ({ page }) => {
    await page.goto('/login')

    await expect(page.getByPlaceholder('empresa@ejemplo.com')).toBeVisible()
    await expect(page.getByPlaceholder('••••••••')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Ingresar' })).toBeVisible()
  })

  test('has link to registration page', async ({ page }) => {
    await page.goto('/login')

    const registerLink = page.getByRole('link', { name: /Regístrate/ })
    await expect(registerLink).toBeVisible()
    await registerLink.click()
    await page.waitForURL('**/register')
    expect(page.url()).toContain('/register')
  })
})

test.describe('Register Page', () => {
  test('loads step 1 with account fields', async ({ page }) => {
    await page.goto('/register')

    await expect(page.getByText('Nombre completo')).toBeVisible()
    await expect(page.getByText('Correo electrónico')).toBeVisible()
    await expect(page.getByText('Contraseña')).toBeVisible()
  })

  test('has link to login page', async ({ page }) => {
    await page.goto('/register')

    const loginLink = page.getByRole('link', { name: /Inicia sesión/ })
    await expect(loginLink).toBeVisible()
    await loginLink.click()
    await page.waitForURL('**/login')
    expect(page.url()).toContain('/login')
  })
})

test.describe('Auth Redirect', () => {
  test('unauthenticated user is redirected to /login', async ({ page }) => {
    await page.context().clearCookies()
    await page.goto('/')
    await page.waitForURL('**/login')
    await expect(page.getByRole('button', { name: 'Ingresar' })).toBeVisible()
  })
})

test.describe('Login Flow', () => {
  test('submits login form and handles response', async ({ page }) => {
    await page.goto('/login')

    await page.getByPlaceholder('empresa@ejemplo.com').fill(process.env.E2E_TEST_EMAIL || 'test@ferreteria.com')
    await page.getByPlaceholder('••••••••').fill(process.env.E2E_TEST_PASSWORD || 'Test12345!')
    await page.getByRole('button', { name: 'Ingresar' }).click()

    // Wait for either redirect to dashboard or error message
    await Promise.race([
      page.waitForURL('/'),
      page.getByText(/incorrectos|error/i).waitFor({ timeout: 10000 }),
    ])
  })
})
