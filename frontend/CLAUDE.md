# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Comandos de Desarrollo

```bash
pnpm dev                    # Dev server en puerto 3000
pnpm build                  # Production build
pnpm lint                   # ESLint

# Tests E2E (Playwright) — requiere dev server corriendo o lo levanta automático en puerto 3001
pnpm test:e2e               # Headless
pnpm test:e2e:ui            # Con inspector UI
pnpm test:e2e:headed        # Con browser visible

# Un solo test
npx playwright test e2e/auth.spec.ts
npx playwright test e2e/auth.spec.ts -g "nombre del test"
```

El backend debe estar corriendo en `http://localhost:8000` para que el frontend funcione (variable `NEXT_PUBLIC_API_URL`).

## Arquitectura

### Stack
- **Next.js 14** con App Router, React 18, TypeScript strict
- **shadcn/ui** (estilo `base-nova`) + Tailwind CSS 3 + Radix UI primitives
- **TanStack Query v5** para data fetching/mutations
- **React Hook Form + Zod v4** para formularios
- **Recharts v3** para gráficas (bar, line, pie, area, radar, metric, table)
- **Playwright** para tests e2e

### Estructura de Carpetas Clave

- `src/app/(auth)/` — Login y registro (portada en dos paneles: marca y formulario)
- `src/app/(dashboard)/` — App principal: inicio (`/`), datos y cargue (`/data`), tableros (`/dashboards`), configuración (`/settings`)
- `src/lib/upload/` — Flujo de cargue: validación local, lectores CSV/JSON/XLSX sin dependencias, evaluación (¿revisar o guardar directo?), primer vistazo y máquina de estados
- `src/hooks/` — Custom hooks que wrappean TanStack Query por dominio: `use-auth`, `use-files`, `use-dashboards`, `use-agents`, `use-etl`, `use-templates`, `use-floating-chat`
- `src/lib/api.ts` — Cliente HTTP centralizado con `credentials:'include'` en todos los fetch; los tokens viven en cookies HttpOnly seteadas por el backend (`access_token` path=/, `refresh_token` path=/api/v1/auth/refresh). El frontend nunca toca tokens directamente.
- `src/types/api.ts` — Tipos TypeScript para toda la API (User, Dashboard, WidgetConfig, ChatMessage, etc.)
- `src/providers/` — `AuthProvider` (hace `useQuery(['auth','me'])` contra `GET /api/v1/auth/me` para obtener el usuario actual; sin decode local de JWT) y `QueryProvider` (TanStack)
- `src/components/charts/` — `ChartRenderer` renderiza cualquier tipo de gráfica desde un `WidgetConfig`
- `src/components/chat/` — `FloatingChat` panel lateral integrado en el dashboard layout

### Flujo de Autenticación

1. `useAuth()` hook maneja signIn/signUp/signOut contra `/api/v1/auth/*`
2. Tokens viven en cookies HttpOnly seteadas por el backend (`access_token` path=/, `refresh_token` path=/api/v1/auth/refresh). El frontend nunca lee ni escribe tokens.
3. `middleware.ts` redirige: sin cookie → `/login`; con cookie en ruta pública → `/`
4. `AuthProvider` hace `useQuery(['auth','me'])` contra `GET /api/v1/auth/me` para obtener `user_id`, `org_id`, `email`, `role`, `full_name`. Sin decode local de JWT.
5. `signIn`/`signUp` invalidan `['auth','me']` después del login. `signOut` llama `POST /api/v1/auth/logout` y hace `queryClient.clear()`.
6. `api.ts` usa `credentials:'include'` en todos los fetch; el browser envía la cookie automáticamente.

### Patrón de Hooks de Datos

Cada dominio tiene hooks en `src/hooks/` que siguen el mismo patrón:
- **Queries**: `useFiles()`, `useDashboards()`, `useAgentSessions()` — wrappean `useQuery` con query keys consistentes
- **Mutations**: `useUploadFile()`, `useCreateDashboard()`, `useRunAnalysis()` — wrappean `useMutation` e invalidan las query keys relacionadas en `onSuccess`
- El polling automático se usa para procesos async: `useAgentSession` hace refetch cada 3s mientras el status sea `pending`/`running`; `useETLJobs` hace refetch cada 5s

### Chat Flotante

`useFloatingChat()` gestiona estado local (no TanStack Query):
- Carga historial de `/api/v1/chat/history` una sola vez
- Mensajes optimistas: se agregan inmediatamente y se remueven si falla el envío
- Soporta envío de archivos via FormData a `/api/v1/chat/upload`
- Contexto por página: cambia el placeholder según la ruta actual

- El estado del chat vive en `ChatProvider` (`src/providers/chat-provider.tsx`): una sola conversación para toda la app, `ask(pregunta)` abre el chat desde cualquier pantalla y Ctrl/Cmd+K lo abre o cierra.
- Los errores del chat pasan por `src/lib/chat-errors.ts` (429 de límite/cuota con el texto restaurado al cuadro) y el resto por el traductor central `src/lib/errors.ts`.

### Sistema de diseño (Brújula)

- Identidad en `src/config/brand.ts` (nombre, frase, crédito). Cambiar el nombre ahí lo cambia en toda la UI.
- Tokens HSL en `globals.css` con roles semánticos y tres variantes por estado (`success`/`warning`/`danger`/`info`/`highlight`: sólido, `-soft` fondo, `-strong` texto AA). Primario verde azulado profundo `#11604F`, acento azafrán `#E3A11B`, papel cálido `#F7F4EE`. Modo oscuro con la clase `.dark` (ThemeProvider de `next-themes`).
- Gráficos: 8 colores categóricos en orden fijo (`--chart-1..8`), validados para daltonismo en claro y oscuro; usar `SimpleChart` (`src/components/charts/simple-chart.tsx`).
- Tipografía: Fraunces (`font-display`, titulares y cifras grandes) + Plus Jakarta Sans (UI) vía `next/font/google`.
- Componentes propios en `src/components/kit/` (encabezado, cifra, frase de dato, avisos, pasos, estados vacíos, zona de arrastre…). Textos de cara al usuario: español, tuteo, sin jerga técnica; todo error pasa por `humanizeError`.
- Rejillas con `auto-grid` (se adaptan al ancho disponible, también con el chat abierto).

### Widget / Dashboard System

Los dashboards contienen `WidgetConfig[]`. Cada widget tiene: `chart_type` (bar/line/pie/area/radar/metric/table), `x_key`, `y_keys`, `data`, `width` (1-4 cols), `height` (1-2 rows). `ChartRenderer` en `src/components/charts/chart-renderer.tsx` maneja el dispatch por tipo.

## Convenciones

- Path alias: `@/*` → `./src/*`
- Server Components por defecto; `"use client"` solo cuando se necesita interactividad
- Iconos: `lucide-react`
- Toasts: `sonner` via el componente `<Toaster>` en el root layout
- Nuevos componentes UI: agregar con `npx shadcn@latest add <component>`
- Todos los endpoints de la API están bajo `/api/v1/` — el prefijo lo pone el backend
