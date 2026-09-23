/**
 * Playwright E2E — Flujo completo de autenticación contra el VPS de producción.
 *
 * Target: https://dashboard-ia-ucompensar.187.124.64.227.nip.io
 *   (path-based routing: /api/* → backend, resto → frontend)
 *
 * Verifica:
 *   1. Login via formulario real con credenciales de prueba
 *   2. Cookies HttpOnly + Secure + SameSite=strict
 *   3. Tokens NO presentes en localStorage
 *   4. Dashboard renderiza tras login
 *   5. Navegación a secciones principales
 *   6. GET /api/v1/auth/me retorna el user
 *
 * Nota: usa page-based requests (Chromium) para respetar `--host-resolver-rules`
 * del launchOptions. No usa page.request.* (Node resolver).
 */
import { test, expect, type Page, type BrowserContext } from "@playwright/test"

const FRONTEND_URL = "https://dashboard-ia-ucompensar.187.124.64.227.nip.io"
const EMAIL = "ferreteria@gmail.com"
const PASSWORD = "Prueba123*"

async function loginViaUI(page: Page): Promise<void> {
  await page.goto(`${FRONTEND_URL}/login`)
  await page.waitForSelector('input[type="email"]', { timeout: 15000 })
  await page.fill('input[type="email"]', EMAIL)
  await page.fill('input[type="password"]', PASSWORD)
  await page.click('button[type="submit"]')
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), {
    timeout: 20000,
  })
}

async function getVpsCookies(context: BrowserContext) {
  // Pass no URL → devuelve TODAS las cookies del contexto independiente del path.
  return context.cookies()
}

test.describe("VPS — Flujo completo HttpOnly cookies (HTTPS)", () => {
  test("frontend /login responde 200 via HTTPS", async ({ page }) => {
    const response = await page.goto(`${FRONTEND_URL}/login`)
    expect(response?.status()).toBe(200)
    // Verifica que venimos por HTTPS (no redirect insecure)
    expect(page.url()).toMatch(/^https:/)
  })

  test("HTTP redirige a HTTPS automáticamente", async ({ page }) => {
    const response = await page.goto(
      "http://dashboard-ia-ucompensar.187.124.64.227.nip.io/login"
    )
    expect(page.url()).toMatch(/^https:/)
    expect(response?.status()).toBe(200)
  })

  test("login completo con ferreteria@gmail.com + screenshots", async ({
    page,
    context,
  }) => {
    // Step 1 — Abrir la página de login
    await page.goto(`${FRONTEND_URL}/login`)
    await page.waitForSelector('input[type="email"]', { timeout: 15000 })
    await page.screenshot({
      path: "test-results/vps-01-login-page.png",
      fullPage: true,
    })

    // Step 2 — Llenar credenciales
    await page.fill('input[type="email"]', EMAIL)
    await page.fill('input[type="password"]', PASSWORD)
    await page.screenshot({
      path: "test-results/vps-02-login-filled.png",
      fullPage: true,
    })

    // Step 3 — Submit y esperar redirect
    await page.click('button[type="submit"]')
    await page.waitForURL((url) => !url.pathname.startsWith("/login"), {
      timeout: 20000,
    })
    await page.waitForLoadState("networkidle", { timeout: 15000 })
    await page.screenshot({
      path: "test-results/vps-03-dashboard.png",
      fullPage: true,
    })

    // Step 4 — Verificar cookies HttpOnly + Secure + SameSite
    const cookies = await getVpsCookies(context)
    const access = cookies.find((c) => c.name === "access_token")
    const refresh = cookies.find((c) => c.name === "refresh_token")

    expect(access, "access_token cookie debe existir").toBeDefined()
    expect(access?.httpOnly, "access_token debe ser HttpOnly").toBe(true)
    expect(access?.secure, "access_token debe ser Secure (HTTPS)").toBe(true)
    expect(
      (access?.sameSite || "").toLowerCase(),
      "access_token debe ser SameSite=Strict"
    ).toBe("strict")

    expect(refresh, "refresh_token cookie debe existir").toBeDefined()
    expect(refresh?.httpOnly, "refresh_token debe ser HttpOnly").toBe(true)
    expect(refresh?.secure, "refresh_token debe ser Secure (HTTPS)").toBe(true)
    expect(
      refresh?.path,
      "refresh_token debe tener path restringido"
    ).toContain("/api/v1/auth/refresh")

    // Step 5 — Verificar que NO hay tokens en localStorage
    const lsAccess = await page.evaluate(() =>
      localStorage.getItem("access_token")
    )
    const lsRefresh = await page.evaluate(() =>
      localStorage.getItem("refresh_token")
    )
    expect(lsAccess, "access_token NO debe estar en localStorage").toBeNull()
    expect(lsRefresh, "refresh_token NO debe estar en localStorage").toBeNull()

    // Step 6 — No redirect de vuelta a /login
    expect(page.url()).not.toContain("/login")
  })

  test("navegación: /data — mis datos", async ({ page }) => {
    await loginViaUI(page)
    await page.goto(`${FRONTEND_URL}/data`)
    await page.waitForLoadState("networkidle", { timeout: 15000 })
    await page.screenshot({
      path: "test-results/vps-04-data.png",
      fullPage: true,
    })
    expect(page.url()).toContain("/data")
  })

  test("navegación: /dashboards — tableros", async ({ page }) => {
    await loginViaUI(page)
    await page.goto(`${FRONTEND_URL}/dashboards`)
    await page.waitForLoadState("networkidle", { timeout: 15000 })
    await page.screenshot({
      path: "test-results/vps-05-dashboards.png",
      fullPage: true,
    })
    expect(page.url()).toContain("/dashboards")
  })

  test("navegación: /settings — configuración", async ({ page }) => {
    await loginViaUI(page)
    await page.goto(`${FRONTEND_URL}/settings`)
    await page.waitForLoadState("networkidle", { timeout: 15000 })
    await page.screenshot({
      path: "test-results/vps-06-settings.png",
      fullPage: true,
    })
    expect(page.url()).toContain("/settings")
  })

  test("GET /api/v1/auth/me retorna user tras login", async ({ page }) => {
    await loginViaUI(page)

    // Fetch /me usando el browser (mismo origin, respeta DNS override).
    const meData = await page.evaluate(async (url) => {
      const res = await fetch(`${url}/api/v1/auth/me`, {
        credentials: "include",
      })
      return {
        ok: res.ok,
        status: res.status,
        body: res.ok ? await res.json() : null,
      }
    }, FRONTEND_URL)

    expect(meData.ok, `GET /me debe retornar 2xx, got ${meData.status}`).toBe(
      true
    )
    expect(meData.body?.email, "email en /me debe coincidir").toBe(EMAIL)
  })
})
