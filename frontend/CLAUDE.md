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
- `src/app/(dashboard)/` — App principal: inicio (`/`), resumen de la semana (`/resumen`), datos y cargue (`/data`), tableros (`/dashboards`), configuración (`/settings`)
- `src/lib/upload/` — Validación local de archivos (tipo, tamaño, .xlsx real) y lectores CSV/JSON/XLSX sin dependencias
- `src/lib/intake/` + `src/components/data/intake/` — CARGA INTELIGENTE: una sola zona para soltar varios archivos (`IntakeZone`), estado por archivo (leyendo → entendiendo → listo), panel «Esto es lo que entendí» (`SheetCard`), corrección de tipo/roles con desplegables, «Con esto ya puedo decirte…» (`UnlocksPanel`, sale de GET /insights) y «Deshacer». Lógica pura en `plan.ts` (qué pide ayuda, plan que se confirma) y `state.ts` (reducer). Contrato en `src/types/intake.ts`: `POST /api/v1/intake/analyze` → `POST /api/v1/intake/commit` (se reenvían los mismos archivos) → `POST /api/v1/intake/undo`; `GET /api/v1/intake/ontology`; `PUT /api/v1/schema/tables/{id}/roles`. Solo se pide ayuda con baja confianza o duda de mezcla; si todo es claro se guarda directo.
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

### Sistema de diseño (Proyecto PI0320251)

- Identidad en `src/config/brand.ts` (nombre "Proyecto PI0320251", código, frase, institución). Cambiar el nombre ahí lo cambia en toda la UI. El wordmark es de dos niveles (`BrandName` en `kit/logo.tsx`): "PROYECTO" pequeño en mayúsculas espaciadas y "PI0320251" en Outfit. El isotipo (aguja de brújula sobre baldosa naranja) se conserva como símbolo. Clave interna de localStorage `brujula.chat.open` se deja igual a propósito (cambiarla borraría la preferencia guardada).
- Colores de la Fundación Universitaria Compensar: **blanco y naranja**. Tokens HSL en `globals.css` con roles semánticos y tres variantes por estado (`success`/`warning`/`danger`/`info`/`highlight`: sólido, `-soft` fondo, `-strong` texto AA).
  - `highlight` = naranja PURO del logo `#ED6824`: solo decorativo/grande (iconos, puntos, resaltados, 1.ª serie de gráficos). Blanco encima da 3,18:1: nunca texto blanco pequeño sobre él.
  - `primary` = naranja INTERACTIVO `#C44A0E` (botones, enlaces, chips activos; blanco encima 4,85:1). Hover con `bg-primary-hover` (`#AE420B`), nunca `bg-primary/90` (aclarar baja el contraste).
  - Fondo blanco `#FFFFFF`, superficies secundarias gris cálido (`#F7F4F1`, barra lateral `#FBF9F7`), tinta `#1F1A17`. Paneles de marca (`bg-brand`) melocotón muy suave `#FFF5EE`.
  - Estados lejos del naranja: éxito verde, advertencia ámbar amarillo `#D9A20B` (con icono), error carmesí `#C42B3F`, info azul. El naranja nunca va solo: siempre con icono y texto.
  - Modo oscuro (clase `.dark`, `next-themes`): carbón cálido `#161311`, texto `#F3EEE9`, primario `#EE6F2C` con texto tinta (6,15:1).
- Motivo firma: la retícula de puntos del logo (`src/components/kit/dots.tsx`): `DotField` (textura de fondo, clase `.bg-dots`), `DotCluster` (racimo decorativo), `DotRule` (separador) y `DotsLoader` ("puntos que se encienden", para cargas). El isotipo es la brújula (`BrandMark`) en baldosa naranja.
- Logo oficial de la universidad con `UniversityLogo` (`kit/logo.tsx`, archivo `public/logo-ucompensar.png`): login, pie de la barra lateral y Configuración › Acerca de. No se recolorea ni se recorta; en oscuro va sobre una placa blanca.
- Gráficos: 8 colores categóricos en orden fijo (`--chart-1..8`: naranja, azul, verde azulado, ciruela, oro, celeste, verde, violeta), validados con el validador de la skill `dataviz` en claro y oscuro (CVD adyacente ΔE ≥ 8, visión normal ≥ 15, contraste ≥ 3:1); usar `SimpleChart` (`src/components/charts/simple-chart.tsx`).
- Tipografía: **Outfit** (`font-display`: titulares y cifras grandes; geométrica y redonda como la letra del logo) + **Inter** (`font-sans`: toda la interfaz, la más legible en tamaño pequeño) vía `next/font/google` (variables, subconjunto `latin`, `display: swap`, respaldo a fuentes del sistema).
  - Cambiar de par es UNA línea en `src/config/fonts.ts`:
    - A (predeterminado): `export { fontPair } from "./font-pairs/outfit-inter"`
    - B: `export { fontPair } from "./font-pairs/sora-dm-sans"` (ojo: DM Sans no trae cifras tabulares; las tablas no alinean)
    - C: `export { fontPair } from "./font-pairs/urbanist-inter"` (ojo: Urbanist no trae cifras tabulares; los KPI no alinean)
  - Cada par define en `src/config/font-pairs/*.ts` su espaciado de texto (`--tracking-body`) y rasgos OpenType (`--font-features`).
  - Reglas: cifras siempre lining (nunca de estilo antiguo); `tabular` (tabular-nums) en tablas, ejes y KPIs; texto con espaciado normal e interlineado 1,55; el espaciado negativo de `.font-display` solo aparece en tamaños grandes (> 20 px) y crece con el tamaño. No usar `tracking-tight` en textos pequeños.
- Componentes propios en `src/components/kit/` (encabezado, cifra, frase de dato, avisos, pasos, estados vacíos, zona de arrastre…). Textos de cara al usuario: español, tuteo, sin jerga técnica; todo error pasa por `humanizeError`.
- Rejillas con `auto-grid` (se adaptan al ancho disponible, también con el chat abierto).
- Tablas con scroll horizontal: el contenedor con `overflow-x-auto` debe ser `relative`. Si no, los textos `sr-only` (posición absoluta) de la tabla escapan del recorte y ensanchan toda la página.
- KPIs del tablero: la unidad la decide `src/lib/kpi.ts`. El signo $ solo aparece con una pista monetaria DEL DATO (`unit` explícita, icono de dinero o columna de origen de dinero), nunca por la etiqueta ("Total Ventas" con icono `Database` es un conteo de filas).
- Columnas de índice (`Index`, `#`, `N°`, `Unnamed: 0`, `*_id`) son `id`: nunca se usan como medida en preguntas sugeridas ni en el primer vistazo.

### Esta semana en tu negocio (hallazgos de plata)

- `GET /api/v1/insights` (sin IA, cálculos exactos del servidor). Tipos en `src/types/insights.ts`, lógica pura en `src/lib/insights.ts` (formato por `unit`, orden por severidad, periodo, texto y enlace de WhatsApp) y hook `useInsights()` (`src/hooks/use-insights.ts`; clave `["insights"]`, se invalida junto con los datos en `use-data.ts`).
- `percent` llega en escala 0-100. El dinero se muestra "$47,6 M" desde un millón y "$360.000" por debajo (sin espacio tras el $, igual que las frases del servidor).
- `InsightCard` (`kit/insight-card.tsx`): severidad = tono + icono + palabra (Importante / Ojo / Dato), nunca solo color. Siempre trae «Ver cómo lo calculé» (pasos, hojas y filas usadas; los avisos `how.notes` se ven en la tarjeta, sin abrir nada). Responde al ANCHO DE LA TARJETA con container queries (`[@container(min-width:26rem)]:`), no al de la pantalla, porque con el chat abierto la tarjeta es angosta aunque la pantalla no lo sea.
- Inicio: `InsightsSection` (top 3, maneja cargando / error / solo faltantes / vacío sin tumbar el resto) y `AskBox compact`. `/resumen`: todos los hallazgos, «Lo que te falta para ver más», compartir (WhatsApp, copiar, imprimir) y vista previa del mensaje.
- Navegación: «Resumen de la semana» está en el menú lateral y en la barra inferior del celular; Configuración sale de esa barra (queda en el menú de la cuenta) vía `NavItem.mobile = false`.
- Impresión (`@media print` en `globals.css` + clases `print:`): sin barra lateral, barra superior ni chat; el cálculo de cada hallazgo sale abierto (`data-print-open`); las tarjetas no se parten entre páginas; siempre en tema claro (`usePrintInLight` en `app-shell.tsx`).

### Tableros creados por la IA

- **No hay creación manual**: el formulario «Nuevo tablero» se eliminó. Los tableros los arma el asistente: (1) la persona lo pide en el chat («creame un tablero de ventas por mes y por producto») y el servidor declara la herramienta `create_dashboard` solo en esos turnos; (2) «Sugerir tableros» y la sugerencia automática (`POST /api/v1/dashboards/suggest`; `{auto:true}` solo si no hay tableros: Tableros la pide una vez al abrir vacío con datos).
- `/dashboards`: botón «Pídele un tablero al asistente» (abre el chat con una pregunta guía SIN enviarla), «Sugerir tableros», tarjetas con vista previa (`preview` = solo números guardados al crear, `DashboardPreview` decorativo), qué muestra (`highlights`) y quién lo creó (`source`). Estado vacío con 3 pedidos clicables generados SOLO con plantillas locales (`lib/dashboard-examples.ts`, sin IA).
- Chat: el servidor agrega al mensaje un bloque ```dashboard con `{id,name,widgets,existing}`. `lib/dashboard-block.ts` lo valida (UUID obligatorio: sin UUID no hay enlace ni tarjeta) y `DashboardCard` ofrece «Abrir tablero» y «Deshacer»/«Eliminar» (borrado lógico). Al llegar el mensaje se invalida `["dashboards"]` (`ChatProvider` -> `useFloatingChat({ onDashboardCreated })`). El nombre se pinta siempre como texto de React.
- Detalle `/dashboards/[id]`: `POST /execute` devuelve `{charts, kpis, legacy}`. Cada gráfico/cifra trae `unit` ("money" | "count" | "number") decidida por el servidor y manda sobre `isMoneyLike`; un widget con `error` se pinta como aviso en su tarjeta y el resto sigue. Ya no existe «Descargar su código»: el script .py se retiró.
- `WidgetConfig` (contrato de `ChartRenderer`) solo ganó el campo opcional `unit`.

### Detalle al tocar un dato y filtros del tablero (solo lectura, sin IA)

- **Nombres legibles**: el servidor titula con el ROL de la columna ("Ventas por mes", "Total que te deben") o, sin rol, con un humanizador determinista de encabezados (`vr.total` -> "Valor total", `fec` -> "Fecha", `p.unit` -> "Precio unitario"). `lib/data-vocabulary.ts` espeja esas abreviaturas para chips y sugerencias. La unidad `$` sale del ROL monetario (total, precio/costo unitario, valor) aunque el nombre sea raro; sin rol, de palabras de dinero (incluye `debe`, `fiado`, `cartera`). La huella de idempotencia del tablero sigue usando nombres canónicos de columna.
- **Detalle (drill)**: con `chart.drillable` y `chart.id`, cada dato de `SimpleChart` (barra, punto, porción, fila de leyenda y de tabla) es un BOTÓN (`onSelectPoint`): foco por teclado con una sola parada de Tab por gráfico, flechas/Home/End para moverse, Enter/Espacio para abrir, zona tocable mínima de 28 px (`HIT`), cursor y hover en `globals.css` (`.drill-datum`). Dos reglas que costaron un bug real: (1) la parada de Tab vive en una REF y se actualiza en el DOM, no en el estado, porque repintar el gráfico recrea los nodos de Recharts y se tragaba el clic; (2) los dibujos de cada dato son componentes ESTABLES de módulo que leen un contexto. Con detalle el contenedor es `role="group"` (un `role="img"` ocultaría los botones) y la torta NO se vuelve a agrupar en el cliente ("Otros (n)" lo arma el servidor y tiene su propio detalle).
- El valor que se manda es `point.key` (valor EXACTO de la celda; el `name` visible puede estar recortado o con formato de fecha), `null` para «(sin dato)» o `other: true` para «Otros». `lib/drill.ts` (lógica pura) arma la petición; `components/dashboards/drill-panel.tsx` es el panel (hoja inferior al 92 % en el celular, lateral en pantallas grandes) con «Ver por», barras de proporción, estados de carga/vacío/error, Escape y retorno del foco al dato (`captureFocus`). «Preguntar al asistente sobre esto» abre el chat con la pregunta ESCRITA (no enviada).
- **Filtros**: `components/dashboards/filter-bar.tsx` (periodo con atajos y rango, hasta 3 categorías con búsqueda y fichas «Quitar»). El estado vive en la URL (`?periodo=ultimos-30|este-mes|mes-anterior|este-anio|todo`, `?desde=&hasta=`, `?f_<categoria>=valor` repetido; lógica pura y validada en `lib/dashboard-filters.ts`). `useDashboardExecute(id, filters)` manda `{filters}` a `POST /execute` (los filtros se SUMAN a los de cada widget, no se guardan); `useDashboardFilterOptions` lee `GET /filter-options` (valores más frecuentes + `?key=&q=` para buscar). Un widget sin la fecha o la categoría se calcula sin ese filtro y avisa con `notes`; sin filas es un estado vacío (`empty`), no un error. El detalle respeta los filtros activos.
- Encabezados de página con container query (`[container-type:inline-size]` + `[@container(min-width:44rem)]:`): responden al ancho del CONTENIDO, no al de la pantalla (con el chat abierto a 1280 px el título quedaba a una palabra por línea).

### Editar tableros con el asistente

- El asistente (Gemini) puede agregar, reemplazar o quitar gráficos y renombrar un tablero que ya existe. El servidor agrega al mensaje un bloque ```dashboard_edit con `{id,name,widgets,version,noop,renamed,added,replaced,removed,unchanged}` (listas de máx. 6 títulos de <= 80 caracteres; `version` es null cuando `noop` es true). `lib/dashboard-edit-block.ts` lo valida como entrada no confiable (UUID obligatorio en `id` y `version`, listas acotadas, todo texto como texto de React) y trae `editSummary`/`editHeadline` («agregué 1 gráfico, quité 2, reemplacé 1, cambié el nombre»). `MESSAGE_BLOCK` y `hasDashboardBlock` (`lib/dashboard-block.ts`) reconocen también `dashboard_edit`; `isUuid` vive en `lib/uuid.ts` para evitar un import circular.
- `DashboardEditCard` (`components/chat/`): mismo lenguaje que `DashboardCard`; lista de cambios con icono Y palabra (Agregué / Quité / Reemplacé / Cambié el nombre / Ya estaba), «Abrir tablero» y «Deshacer» con `ConfirmDialog`. Estados: normal, deshecho (atenuado, sigue pudiendo abrirse), 404 («Este cambio ya no se puede deshacer»), tablero eliminado («Ya no existe el tablero»), sin cambios (`noop`: sin «Deshacer») y error (toast humanizado, la tarjeta sigue usable). La frase de estado va en una región `aria-live="polite"` siempre montada.
- `POST /api/v1/dashboards/{id}/undo-edit` con `{version, include_newer}` (hook `useUndoDashboardEdit`). 409 con `detail = {code:"newer_edits", count}`: el MISMO diálogo cambia a «¿Deshacer también los cambios más recientes?» y confirmar reenvía con `include_newer:true` (`newerEditsInfo` lee el 409). Cualquier otro error pasa por `humanizeError`. `GET /api/v1/dashboards/{id}/versions` existe pero la UI no lo usa.
- Invalidación: `invalidateDashboard(queryClient, id)` (`use-dashboards.ts`) refresca `["dashboards"]`, `["dashboard-meta", id]` y `["dashboard-execute", id]`. Se llama al aplicar el cambio (`ChatProvider` -> `useFloatingChat({ onDashboardsEdited })`, solo si no es `noop`) y al deshacer.
- Gotchas: (1) el diálogo está en un portal pero los eventos de React suben por el árbol: la tarjeta detiene el Escape para que no cierre el chat que la contiene. (2) `ConfirmDialog` no tiene «Trigger», así que Radix no devuelve el foco al cerrar: la tarjeta lo devuelve a mano cuando el diálogo ya desapareció (`focusSoon`). (3) `ChatProvider.ask(texto, {send:false})` conserva el espacio final (la persona sigue escribiendo justo después de la frase guía).
- Detalle `/dashboards/[id]`: `EditWithAssistantButton` (`components/dashboards/`) «Pídele al asistente que lo edite» abre el chat con `Quiero editar el tablero «{nombre}»: ` SIN enviarla (nombre en una línea, sin « », máx. 80 caracteres). Va bajo la descripción del título, no entre las acciones: con el chat abierto el encabezado es angosto y tres botones lo aplastaban.

## Convenciones

- Path alias: `@/*` → `./src/*`
- Server Components por defecto; `"use client"` solo cuando se necesita interactividad
- Iconos: `lucide-react`
- Toasts: `sonner` via el componente `<Toaster>` en el root layout
- Nuevos componentes UI: agregar con `npx shadcn@latest add <component>`
- Todos los endpoints de la API están bajo `/api/v1/` — el prefijo lo pone el backend
