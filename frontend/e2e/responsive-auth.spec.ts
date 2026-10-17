import { test, expect } from "@playwright/test"

test.describe("auth pages — responsive smoke", () => {
  test("login viewport meta + no horizontal overflow", async ({ page }) => {
    await page.goto("/login")

    const viewportContent = await page
      .locator('meta[name="viewport"]')
      .getAttribute("content")
    expect(viewportContent).toContain("width=device-width")
    expect(viewportContent).toContain("initial-scale=1")

    const hasOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1,
    )
    expect(hasOverflow).toBe(false)

    await expect(page.getByRole("heading", { name: "Qué bueno verte" })).toBeVisible()
    await expect(
      page.getByPlaceholder("empresa@ejemplo.com"),
    ).toBeVisible()
  })

  test("register viewport meta + no horizontal overflow", async ({ page }) => {
    await page.goto("/register")

    const hasOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1,
    )
    expect(hasOverflow).toBe(false)

    await expect(page.getByRole("heading", { name: "Crea tu cuenta" })).toBeVisible()
  })
})
