import { test, expect } from '@playwright/test'

test.setTimeout(600_000)

test('login + navegacion a tableros', async ({ page }) => {
  await page.goto('/login', { waitUntil: 'domcontentloaded' })

  const email = page.locator('input[type="email"]')
  const password = page.locator('input[type="password"]')
  await email.waitFor({ state: 'visible', timeout: 30_000 })

  // Espera a que React hidrate antes de interactuar con el form.
  await page.waitForLoadState('load')
  await page.waitForTimeout(2000)

  await email.click()
  await email.fill('ferreteria@gmail.com')
  await password.click()
  await password.fill('Prueba123*')

  // Dispara la respuesta POST /auth/login y espera la salida de /login.
  await Promise.all([
    page.waitForResponse(
      (r) => r.url().includes('/api/v1/auth/login') && r.request().method() === 'POST',
      { timeout: 30_000 },
    ),
    page.getByRole('button', { name: /ingresar/i }).click(),
  ])

  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 30_000 })

  await page.goto('/dashboards', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('heading', { name: /tableros/i })).toBeVisible({ timeout: 30_000 })
  await page.waitForTimeout(2500)
  await page.screenshot({ path: 'test-results/01-lista-tableros.png', fullPage: true })

  const verTableroLinks = page.locator('a[href^="/dashboards/"]')
  const total = await verTableroLinks.count()
  console.log('Tableros visibles:', total)

  // Recorre cada tablero, entra al detalle, espera carga y captura
  for (let i = 0; i < total; i++) {
    // Re-localiza tras cada navegación
    await page.goto('/dashboards', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(1500)

    const link = page.locator('a[href^="/dashboards/"]').nth(i)
    const href = await link.getAttribute('href')
    const cardName = await link.locator('xpath=ancestor::*[contains(@class,"flex")][1]').textContent().catch(() => '')
    console.log(`\n[${i + 1}/${total}] Entrando a ${href}`)

    await link.click()
    await page.waitForURL(/\/dashboards\/[^/]+$/, { timeout: 20_000 })

    // Espera ejecución (POST /execute) — máx 60s, captura resultado
    try {
      await page.waitForResponse(
        (r) => r.url().includes('/execute') && r.request().method() === 'POST',
        { timeout: 60_000 },
      )
      console.log('  ✓ POST /execute completó')
    } catch {
      console.log('  ⚠ POST /execute no llegó en 60s')
    }

    // Espera a que aparezcan charts o el estado vacío
    await page.waitForTimeout(3000)

    const charts = await page.locator('.recharts-wrapper').count()
    const kpis = await page.locator('text=/^\\d[\\d,.]*$/').count()
    const errorMsg = await page.getByText(/error al ejecutar|no hay graficos/i).count()
    console.log(`  charts=${charts}  kpis=${kpis}  vacioOerror=${errorMsg}`)

    const safe = (href ?? `dashboard-${i}`).replace(/\W+/g, '-').slice(-30)
    await page.screenshot({
      path: `test-results/02-tablero-${i + 1}${safe}.png`,
      fullPage: true,
    })
  }

  console.log('\n--- FIN ---')
})
