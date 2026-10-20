// @vitest-environment node
import { describe, expect, test } from "vitest"
import { NextRequest } from "next/server"
import { middleware } from "./middleware"

function request(path: string, cookie?: string): NextRequest {
  return new NextRequest(`http://127.0.0.1:3000${path}`, cookie ? { headers: { cookie } } : undefined)
}

describe("middleware", () => {
  test("should_not_redirect_login_when_an_access_token_cookie_is_present", () => {
    // Una cookie vieja o invalida (otra base de datos, sesion revocada o vencida) NO debe sacar a la persona del login:
    // el middleware no puede validarla y, si redirige, se forma un bucle "/" -> /auth/me 401 -> /login -> "/".
    const res = middleware(request("/login", "access_token=cookie-vieja-invalida"))
    expect(res.headers.get("location")).toBeNull()
    expect(res.status).toBe(200)
  })

  test("should_not_redirect_register_when_an_access_token_cookie_is_present", () => {
    const res = middleware(request("/register", "access_token=cookie-vieja-invalida"))
    expect(res.headers.get("location")).toBeNull()
  })

  test("should_let_login_load_without_a_cookie", () => {
    const res = middleware(request("/login"))
    expect(res.headers.get("location")).toBeNull()
  })

  test("should_let_private_routes_pass_to_the_client_side_guard", () => {
    // La proteccion real de las rutas privadas es del lado del cliente (/auth/me en el layout).
    expect(middleware(request("/")).headers.get("location")).toBeNull()
    expect(middleware(request("/data", "access_token=x")).headers.get("location")).toBeNull()
  })
})
