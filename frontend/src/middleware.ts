import { NextResponse, type NextRequest } from "next/server"

const PUBLIC_ROUTES = ["/login", "/register"]

export function middleware(request: NextRequest): NextResponse {
  const { pathname } = request.nextUrl
  const isPublicRoute = PUBLIC_ROUTES.some((r) => pathname.startsWith(r))

  const token = request.cookies.get("access_token")?.value

  // Nota: esta cookie la pone el BACKEND en su propio dominio. Cuando
  // frontend y backend viven en el mismo sitio (dev local, o produccion
  // detras de un unico dominio/proxy) el middleware la ve y puede redirigir
  // de inmediato, sin parpadeo. Cuando viven en dominios/sitios distintos
  // (ej. dos proyectos separados de Vercel) esta cookie NUNCA es visible
  // aqui, aunque el usuario si este autenticado -- por eso ya no se bloquea
  // el acceso solo por su ausencia; el respaldo real es el chequeo del lado
  // del cliente contra /api/v1/auth/me en (dashboard)/layout.tsx.
  if (token && isPublicRoute) {
    const url = request.nextUrl.clone()
    url.pathname = "/"
    return NextResponse.redirect(url)
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
}
