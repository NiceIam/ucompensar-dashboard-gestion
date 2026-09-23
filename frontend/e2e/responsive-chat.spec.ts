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
  test("mobile: chat cerrado por defecto, FAB visible, overlay abre al tap", async ({
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

    const overlay = page
      .locator('[aria-hidden="true"].fixed.inset-0.bg-black\\/40')
      .first()
    await expect(overlay).toBeVisible()

    await overlay.click({ position: { x: 10, y: 10 }, force: true })
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

  test("desktop: chat pegado al flow, abierto por defecto, sin FAB", async ({
    page,
    viewport,
  }) => {
    test.skip(!viewport || viewport.width < 1024, "desktop-only")

    const panel = page.locator('[role="complementary"][aria-label="Asistente IA"]')
    await expect(panel).toBeVisible()
    await expect(panel).toHaveClass(/lg:w-\[380px\]/)

    const fab = page.getByRole("button", { name: /abrir asistente ia/i })
    await expect(fab).toHaveCount(0)
  })
})
