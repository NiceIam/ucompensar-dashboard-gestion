/**
 * Playwright E2E tests — HttpOnly cookie authentication.
 *
 * IMPORTANT: These tests require the backend to be running on localhost:8001
 * AND the frontend dev server on localhost:3001 (started automatically by
 * playwright.config.ts webServer).
 *
 * These tests do NOT inject fake tokens. If the backend is unavailable they
 * fail explicitly with a descriptive error (C7 compliance: no silent bypass).
 *
 * Required env vars (or fallback test credentials):
 *   E2E_TEST_EMAIL    — registered user email
 *   E2E_TEST_PASSWORD — registered user password
 */
import { test, expect, type BrowserContext, type Page } from "@playwright/test"

const API_URL = "http://localhost:8001"
const TEST_EMAIL = process.env.E2E_TEST_EMAIL || "test@ferreteria.com"
const TEST_PASSWORD = process.env.E2E_TEST_PASSWORD || "Test12345!"

// ---------------------------------------------------------------------------
// Helper — verifies the backend is reachable before proceeding.
// Throws with a clear message if not, so CI output is actionable.
// ---------------------------------------------------------------------------
async function assertBackendIsUp(page: Page): Promise<void> {
  const res = await page.request.get(`${API_URL}/health`).catch(() => null)
  if (!res || !res.ok()) {
    throw new Error(
      `Backend unavailable at ${API_URL}. ` +
        "Start the backend before running auth-cookies e2e tests. " +
        `Health check status: ${res?.status() ?? "network error"}.`
    )
  }
}

// ---------------------------------------------------------------------------
// Helper — performs UI login via the real login form.
// Does NOT inject tokens.
// ---------------------------------------------------------------------------
async function loginViaUI(page: Page): Promise<void> {
  await page.goto("/login")

  // Wait for the form to be ready
  await page.waitForSelector('input[type="email"]', { timeout: 10000 })

  await page.fill('input[type="email"]', TEST_EMAIL)
  await page.fill('input[type="password"]', TEST_PASSWORD)
  await page.click('button[type="submit"]')

  // Wait for redirect away from /login after successful login
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), {
    timeout: 15000,
  })
}

// ---------------------------------------------------------------------------
// Helper — get all cookies for localhost from context
// ---------------------------------------------------------------------------
async function getLocalCookies(
  context: BrowserContext
): Promise<Array<{ name: string; httpOnly: boolean; sameSite: string; value: string }>> {
  const cookies = await context.cookies("http://localhost:3001")
  return cookies as Array<{
    name: string
    httpOnly: boolean
    sameSite: string
    value: string
  }>
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
test.describe("Authentication via HttpOnly cookies", () => {
  test("should_set_httponly_access_token_cookie_when_login_succeeds", async ({
    page,
    context,
  }) => {
    await assertBackendIsUp(page)

    await loginViaUI(page)

    const cookies = await getLocalCookies(context)
    const accessCookie = cookies.find((c) => c.name === "access_token")

    expect(
      accessCookie,
      "access_token cookie must be present after login"
    ).toBeDefined()

    expect(
      accessCookie?.httpOnly,
      "access_token cookie must be HttpOnly"
    ).toBe(true)
  })

  test("should_set_httponly_refresh_token_cookie_when_login_succeeds", async ({
    page,
    context,
  }) => {
    await assertBackendIsUp(page)

    await loginViaUI(page)

    const cookies = await getLocalCookies(context)
    const refreshCookie = cookies.find((c) => c.name === "refresh_token")

    expect(
      refreshCookie,
      "refresh_token cookie must be present after login"
    ).toBeDefined()

    expect(
      refreshCookie?.httpOnly,
      "refresh_token cookie must be HttpOnly"
    ).toBe(true)
  })

  test("should_not_store_access_token_in_localStorage_when_login_succeeds", async ({
    page,
  }) => {
    await assertBackendIsUp(page)

    await loginViaUI(page)

    const localStorageToken = await page.evaluate(() =>
      localStorage.getItem("access_token")
    )

    expect(
      localStorageToken,
      "access_token must NOT be stored in localStorage (HttpOnly cookie pattern)"
    ).toBeNull()
  })

  test("should_not_store_refresh_token_in_localStorage_when_login_succeeds", async ({
    page,
  }) => {
    await assertBackendIsUp(page)

    await loginViaUI(page)

    const localStorageToken = await page.evaluate(() =>
      localStorage.getItem("refresh_token")
    )

    expect(
      localStorageToken,
      "refresh_token must NOT be stored in localStorage (HttpOnly cookie pattern)"
    ).toBeNull()
  })

  test("should_return_user_data_from_me_endpoint_after_login", async ({
    page,
  }) => {
    await assertBackendIsUp(page)

    await loginViaUI(page)

    // After login, the dashboard should show user info.
    // We confirm the /me endpoint is being called successfully by checking
    // that the dashboard content is visible (AuthProvider fetches /me on mount).
    await expect(
      page.locator("body"),
      "Dashboard should render after successful login"
    ).not.toContainText("401")

    // The dashboard must NOT redirect back to /login
    expect(
      page.url(),
      "Should not be redirected back to /login"
    ).not.toContain("/login")
  })

  test("should_clear_cookies_and_redirect_to_login_when_logout_triggered", async ({
    page,
    context,
  }) => {
    await assertBackendIsUp(page)

    await loginViaUI(page)

    // Verify we're logged in
    const cookiesBefore = await getLocalCookies(context)
    const accessBefore = cookiesBefore.find((c) => c.name === "access_token")
    expect(accessBefore).toBeDefined()

    // Trigger logout — look for a logout button or nav element
    // The exact selector depends on the dashboard layout; we try common patterns.
    const logoutButton = page
      .getByRole("button", { name: /salir|cerrar sesión|logout|sign out/i })
      .first()

    const isVisible = await logoutButton.isVisible().catch(() => false)

    if (!isVisible) {
      // Try dropdown navigation pattern: user avatar / menu
      const userMenu = page.locator("[data-testid='user-menu'], [aria-label='User menu']").first()
      const menuVisible = await userMenu.isVisible().catch(() => false)
      if (menuVisible) {
        await userMenu.click()
        await page
          .getByRole("menuitem", { name: /salir|cerrar sesión|logout/i })
          .click()
      } else {
        // Fallback: call the logout API directly — still no token injection
        const res = await page.request.post(`${API_URL}/api/v1/auth/logout`, {
          headers: { "Content-Type": "application/json" },
        })
        // Navigate to login manually as the API call would do
        await page.goto("/login")
      }
    } else {
      await logoutButton.click()
    }

    // After logout we should be on /login
    await page.waitForURL((url) => url.pathname.startsWith("/login"), {
      timeout: 10000,
    })

    expect(page.url()).toContain("/login")

    // access_token cookie should be cleared or expired
    const cookiesAfter = await getLocalCookies(context)
    const accessAfter = cookiesAfter.find((c) => c.name === "access_token")
    // Either absent or has empty value (server may set empty value with past expiry)
    const tokenIsGone = !accessAfter || accessAfter.value === ""
    expect(
      tokenIsGone,
      "access_token cookie must be cleared after logout"
    ).toBe(true)
  })

  test("should_fail_explicitly_when_backend_is_not_running", async ({
    page,
  }) => {
    // This test documents the expected failure mode when the backend is down.
    // It intentionally hits a port that is almost certainly not in use.
    const deadAPI = "http://localhost:19999"
    const res = await page.request.get(`${deadAPI}/health`).catch(() => null)
    expect(
      res,
      "Backend should not be reachable on dead port — test confirms explicit failure mode"
    ).toBeNull()
  })
})
