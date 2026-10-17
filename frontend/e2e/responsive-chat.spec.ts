import { test, expect } from "@playwright/test"

const EMAIL = process.env.SMOKE_EMAIL
const PASSWORD = process.env.SMOKE_PASSWORD

test.beforeEach(async ({ page }) => {
  if (!EMAIL || !PASSWORD) {
    test.skip(true, "SMOKE_EMAIL / SMOKE_PASSWORD env vars required")
  }

  await page.goto("/login")
  await page.locator('input[type="email"]').fill(EMAIL!)
  await page.locator('input[type="password"]').fill(PASSWORD!)
  await page.getByRole("button", { name: /^ingresar$/i }).click()
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), {
    timeout: 15_000,
  })
})

test.describe("FloatingChat — responsive on real VPS", () => {
  // Rediseño Brújula: en el celular el chat ocupa toda la pantalla (sin fondo
  // oscuro) y se cierra con su botón X; el botón para abrirlo vive en la barra inferior.
  test("mobile: chat cerrado por defecto, botón visible, abre a pantalla completa y cierra con X", async ({
    page,
    viewport,
  }) => {
    test.skip(!viewport || viewport.width >= 1024, "mobile-only")

    const fab = page.getByRole("button", { name: /abrir asistente ia/i })
    await expect(fab).toBeVisible({ timeout: 10_000 })

    const panel = page.locator('[role="complementary"][aria-label="Asistente IA"]')
    await expect(panel).toHaveClass(/translate-x-full/)

    await fab.click()
    await expect(panel).toHaveClass(/translate-x-0/)

    await page.getByRole("button", { name: /cerrar el asistente/i }).click()
    await expect(panel).toHaveClass(/translate-x-full/)
    await expect(fab).toBeVisible()
  })

  test("mobile: Escape cierra el chat y regresa foco al FAB", async ({
    page,
    viewport,
  }) => {
    test.skip(!viewport || viewport.width >= 1024, "mobile-only")

    await page.getByRole("button", { name: /abrir asistente ia/i }).click()
    const panel = page.locator('[role="complementary"][aria-label="Asistente IA"]')
    await expect(panel).toHaveClass(/translate-x-0/)

    await page.keyboard.press("Escape")
    await expect(panel).toHaveClass(/translate-x-full/)
    await expect(
      page.getByRole("button", { name: /abrir asistente ia/i }),
    ).toBeFocused()
  })

  test("mobile: dashboard sin overflow horizontal", async ({
    page,
    viewport,
  }) => {
    test.skip(!viewport || viewport.width >= 1024, "mobile-only")

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1,
    )
    expect(overflow).toBe(false)
  })

  // Rediseño Brújula (decisión deliberada): en escritorio el chat sigue acoplado al
  // flujo de la página, pero arranca cerrado la primera vez (para no competir con el
  // contenido) y recuerda la preferencia. Se abre con el botón de la barra lateral o Ctrl+K.
  test("desktop: chat acoplado al flow, se abre desde la barra lateral, sin botón flotante", async ({
    page,
    viewport,
  }) => {
    test.skip(!viewport || viewport.width < 1024, "desktop-only")

    const fab = page.getByRole("button", { name: /abrir asistente ia/i })
    await expect(fab).toBeHidden()

    await page.getByRole("button", { name: /pregúntale a tus datos/i }).first().click()
    const panel = page.locator('[role="complementary"][aria-label="Asistente IA"]')
    await expect(panel).toBeVisible()
    await expect(panel).toHaveClass(/lg:static/)
    await expect(panel).toHaveClass(/lg:w-\[400px\]/)
  })
})
