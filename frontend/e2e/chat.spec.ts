import { test, expect, type Page } from '@playwright/test'

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

  await page.addInitScript((token: string) => {
    localStorage.setItem('access_token', token)
  }, accessToken)
}

test.describe('Chat Page', () => {
  test.beforeEach(async ({ page }) => {
    await loginViaAPI(page)
  })

  test('loads with message input and send button', async ({ page }) => {
    await page.goto('/chat')

    await expect(
      page.getByPlaceholder(/Escriba su pregunta/)
    ).toBeVisible()

    await expect(
      page.getByRole('button', { name: 'Enviar mensaje' })
    ).toBeVisible()
  })

  test('shows empty state with assistant name and suggested questions', async ({ page }) => {
    await page.goto('/chat')

    await expect(page.getByText('Asistente de Datos')).toBeVisible()
    await expect(page.getByText('Preguntas sugeridas:')).toBeVisible()
  })

  test('has attach file button', async ({ page }) => {
    await page.goto('/chat')

    await expect(
      page.getByRole('button', { name: 'Adjuntar archivo' })
    ).toBeVisible()
  })

  test('can type a message in the input', async ({ page }) => {
    await page.goto('/chat')

    const input = page.getByPlaceholder(/Escriba su pregunta/)
    await input.fill('Hola, necesito analizar mis ventas')

    await expect(input).toHaveValue('Hola, necesito analizar mis ventas')
  })

  test('send button enables when text is entered', async ({ page }) => {
    await page.goto('/chat')

    const sendButton = page.getByRole('button', { name: 'Enviar mensaje' })
    const input = page.getByPlaceholder(/Escriba su pregunta/)

    // Send button should be disabled when input is empty
    await expect(sendButton).toBeDisabled()

    // Type something
    await input.fill('Test message')

    // Send button should now be enabled
    await expect(sendButton).toBeEnabled()
  })

  test('clicking a suggested question fills the input', async ({ page }) => {
    await page.goto('/chat')

    const suggestedQuestion = page.getByText(
      '¿Cuál es el producto con más ventas?'
    )
    await suggestedQuestion.click()

    const input = page.getByPlaceholder(/Escriba su pregunta/)
    await expect(input).toHaveValue('¿Cuál es el producto con más ventas?')
  })
})
