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
  // OJO: aqui NO se redirige de /login a "/" por ver una cookie. El middleware no puede saber si la cookie es
  // valida (puede estar vencida, revocada o ser de otra base de datos), y si no lo es se forma un bucle:
  // "/" -> /auth/me 401 -> /login -> "/" ... sin que la persona vea jamas el login. Quien ya tiene una sesion
  // VALIDA se redirige desde la propia pagina de inicio de sesion (usa /auth/me como fuente de verdad).
  void token
  void isPublicRoute

  return NextResponse.next()
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
}
