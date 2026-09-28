# Plan de Trabajo y Cronograma — PI0320251

**Proyecto**: Solución WEB para la gestión estratégica de datos con IA
**Código**: PI0320251 — Fundación Universitaria Ucompensar
**Última actualización**: 27 de septiembre de 2026

## Equipo

| Rol | Responsabilidad principal |
|---|---|
| Desarrollador 1 (semillerista, líder técnico) | Backend, decisiones de arquitectura, tareas de mayor complejidad |
| Desarrollador 2 (semillerista) | Backend/frontend de apoyo, revisión de código, tareas acotadas |
| Pasante 1 — QA / Testing | Pruebas manuales, checklists de casos borde, reporte de bugs |
| Pasante 2 — Documentación | Documentación técnica, diccionario de datos, consolidación |

---

# Fase 1 — Desarrollo base (3 de agosto – 25 de septiembre de 2026)

Trabajo realizado sobre la base de código existente del proyecto, en orden de dependencia técnica.

## Semana 1 (3–7 de agosto): Arquitectura y modelo de datos

- Diseño de la arquitectura multi-tenant: una base de datos PostgreSQL dedicada por organización (`org_<uuid>`), separada de una base de datos principal (`pi_main`) para metadatos globales.
- Definición del esquema de `pi_main`: tablas `organizations`, `users`, `business_types`.
- Definición del esquema base replicado en cada base de datos de organización: `org_data_tables`, `org_data_rows`, `uploaded_files`, `etl_jobs`, `agent_sessions`, `agent_results`, `chat_messages`, `dashboards`, `widgets`.
- Configuración de pools de conexión asíncronos (asyncpg): un pool para la base principal (2-10 conexiones), pools independientes por organización (1-5 conexiones), creados bajo demanda.
- **Entregable**: `backend/app/database.py` con la lógica de inicialización de esquema y creación dinámica de bases de datos por organización.

## Semana 2 (10–14 de agosto): Autenticación y registro

- Implementación de autenticación JWT local (algoritmo HS256), sin dependencia de proveedores externos de auth.
- Endpoints: `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`.
- Tokens entregados como cookies HttpOnly (access_token: 60 min de vigencia; refresh_token: 7 días), nunca expuestos a JavaScript del lado del cliente.
- Rate limiting por endpoint: 5 solicitudes/minuto en registro, 10/minuto en login, 30/minuto en renovación de token.
- Hashing de contraseñas con bcrypt (12 rondas).
- Denylist de tokens revocados (logout) para invalidar sesiones antes de su expiración natural.
- **Entregable**: `backend/app/routers/auth_router.py`, `backend/app/services/auth_service.py`, `backend/app/auth.py`.

## Semana 3 (17–21 de agosto): Tipos de negocio y esquemas por industria

- Definición de 3 tipos de negocio soportados: ferretería, servicios, restaurante.
- Esquema de tablas específico por tipo:
  - **Ferretería**: productos, ventas, proveedores, inventario_movimientos.
  - **Servicios**: servicios, clientes, cotizaciones, facturas.
  - **Restaurante**: menu_items, pedidos, inventario, proveedores.
- Flujo de registro en 3 pasos: datos de cuenta → selección de tipo de negocio → confirmación.
- Endpoint `POST /api/v1/templates/initialize`, que asocia el tipo de negocio elegido a la organización y crea las tablas correspondientes en su base de datos dedicada.
- **Entregable**: `backend/app/services/template_service.py`, semillas de `business_types` en `pi_main`, componente `BusinessTypeSelector` en frontend.

## Semana 4 (24–28 de agosto): Motor de carga inteligente de archivos

- Desarrollo de `schema_agent_service.py`: análisis automático de columnas de un archivo CSV/Excel/JSON, inferencia de tipo de dato por columna (texto, número, fecha), comparación por similitud de texto contra las columnas de tablas ya existentes en la organización.
- Si la similitud supera el umbral configurado, los datos se cargan en la tabla existente (agregando columnas nuevas si hace falta); si no, se crea una tabla nueva automáticamente.
- Endpoint `POST /api/v1/schema/smart-upload`.
- Diseño deliberado sin uso de modelos de lenguaje en esta ruta (matching determinístico), para mantener costos y latencia bajos.
- **Entregable**: pipeline de ingesta de datos funcional para CSV, Excel y JSON.

## Semana 5 (31 de agosto – 4 de septiembre): Interfaz de usuario base

- Configuración de Next.js 14 (App Router) con TypeScript, Tailwind CSS y la librería de componentes shadcn/ui.
- Páginas de autenticación: login y registro (flujo de 3 pasos ya descrito).
- Middleware de protección de rutas basado en la presencia de la cookie de sesión.
- Cliente HTTP centralizado (`lib/api.ts`) con manejo de renovación automática de token ante una respuesta 401.
- **Entregable**: `frontend/src/app/(auth)/*`, `frontend/src/middleware.ts`, `frontend/src/lib/api.ts`, librería base de componentes UI.

## Semana 6 (7–11 de septiembre): Generación automática de dashboards

- Desarrollo de `dashboard_script_service.py`: generación heurística de visualizaciones a partir de los datos cargados — columna de texto + columna numérica → gráfica de barras; columna de fecha + numérica → gráfica de línea; columna categórica → gráfica de pie.
- Generación de un script Python descargable por cada tablero, ejecutable de forma independiente.
- Renderizado de gráficas en el frontend con la librería Recharts.
- Endpoints de creación, listado, ejecución y eliminación de tableros y sus widgets.
- **Entregable**: `frontend/src/app/(dashboard)/dashboards/*`, `frontend/src/components/charts/chart-renderer.tsx`, `backend/app/services/dashboard_script_service.py`.

## Semana 7 (14–18 de septiembre): Asistente conversacional con IA

- Integración con Google Gemini a través del SDK `google-genai`.
- `agent_tools_service.py`: construcción de contexto para el modelo inyectando datos reales de la organización (tablas, conteos, muestras de registros) en el prompt.
- Componente de chat flotante con soporte de formato enriquecido en las respuestas: negritas, listas, tablas y encabezados en markdown.
- Respuesta local de respaldo (sin IA) cuando no hay una llave de API configurada, para no dejar al usuario sin respuesta.
- **Entregable**: `frontend/src/components/chat/floating-chat.tsx`, `backend/app/services/agent_tools_service.py`, `backend/app/services/chat_service.py`.

## Semana 8 (21–25 de septiembre): Estabilización, corrección de errores y despliegue a producción

- Auditoría completa del sistema (revisión exhaustiva de frontend, servicios de backend e infraestructura).
- Corrección de 5 errores críticos encontrados:
  1. Eliminación de una tabla fallaba siempre por uso indebido de una función de agregación dentro de una cláusula `RETURNING` (no soportado por PostgreSQL).
  2. Filas duplicadas en la metadata de tablas de organización, por ausencia de una restricción de unicidad — se agregó la restricción y una migración automática que fusiona duplicados existentes sin perder datos.
  3. Condición de carrera al crear una tabla nueva (dos solicitudes simultáneas podían crear la misma tabla dos veces) — resuelto con una operación atómica a nivel de base de datos.
  4. Carga de archivos sin transacción — una fila fallida a mitad de archivo podía dejar datos parciales sin revertir.
  5. El token de actualización de sesión (refresh token) no se revocaba al rotarlo — un token robado seguía siendo válido hasta su expiración natural (7 días).
- Actualización de dependencias: `google-adk` de la versión 0.3.0 a la 2.9.2; retiro completo del paquete `google-generativeai` (anunciado oficialmente sin soporte) en favor de `google-genai`; actualización del modelo de Gemini utilizado (el modelo anterior fue dado de baja por Google) a `gemini-3.6-flash`.
- Inicialización de control de versiones (Git) y creación del repositorio remoto en GitHub, con historial organizado por módulo.
- Despliegue en producción: backend y frontend en Vercel (como dos proyectos separados), base de datos PostgreSQL en Neon.
- Corrección de dos incompatibilidades propias de un despliegue con frontend y backend en dominios distintos: negociación SSL con el proveedor de base de datos, y política de cookies entre sitios distintos (`SameSite`) para que la sesión de usuario funcione correctamente entre los dos dominios.
- Configuración de tablero de seguimiento del equipo (GitHub Issues + GitHub Projects) con el backlog de trabajo pendiente.
- **Entregable**: sistema desplegado y accesible públicamente; backlog de trabajo pendiente documentado y priorizado (10 tareas iniciales).

---

# Fase 2 — Sprint final (28 de septiembre – 16 de octubre de 2026)

Tres semanas de trabajo, distribuidas por persona según el backlog ya definido en GitHub Issues (#1 a #10 del repositorio). Cada tarea incluye sus criterios de aceptación.

## Semana 1 (28 de septiembre – 2 de octubre)

### Desarrollador 1

**Lunes–martes: Issue #1 — Decisión: pipeline de IA de insights automáticos**
- Actividad: revisar con el equipo si se reconecta el pipeline de 4 agentes (actualmente desconectado por un error de importación) o se elimina el código.
- Criterio de aceptación: decisión documentada por escrito (en el propio issue de GitHub) con la justificación; si se decide reconectar, issue de seguimiento creado con el desglose de esa tarea.

**Miércoles–viernes: Issue #4 (parte 1) — Tests para `schema_agent_service.py`**
- Actividad: escribir pruebas automatizadas para `analyze_csv`, `find_matching_table`, `create_table`, `load_csv_to_table`.
- Criterio de aceptación: cobertura de los casos ya identificados como críticos (creación concurrente de tablas, carga con fila inválida a mitad de archivo); suite ejecuta en verde localmente y en cada push.

### Desarrollador 2

**Lunes (primera hora): Issue #10 — Rotar contraseña de Neon**
- Actividad: generar nueva contraseña desde el dashboard de Neon, actualizar la variable de entorno en Vercel, confirmar que el backend sigue conectando.
- Criterio de aceptación: contraseña anterior invalidada; login de prueba exitoso contra la base de datos con la contraseña nueva.

**Martes–jueves: Issue #3 — Bug: mapeo sector → tipo de negocio roto en el registro**
- Actividad: corregir `auth_service.py` para que el tipo de negocio real se derive correctamente en el registro inicial, sin depender del paso posterior de `/templates/initialize` para corregirlo.
- Criterio de aceptación: una organización nueva que elige "ferretería" no debe terminar con tablas de "servicios" duplicadas.

**Viernes: apoyo en revisión de código (Pull Requests) de Desarrollador 1**

### Pasante 1 — QA/Testing

**Lunes–martes: Issue #5 — Diseño del checklist de carga de archivos**
- Actividad: redactar el checklist de casos de prueba (Excel con varias hojas, CSV con caracteres especiales, archivo vacío, archivo que excede 10.000 filas, columnas que no calzan con ninguna tabla existente).
- Criterio de aceptación: checklist documentado en el issue, revisado por Desarrollador 1.

**Miércoles–viernes: ejecución del checklist**
- Actividad: ejecutar cada caso contra el entorno de producción, registrar resultados.
- Criterio de aceptación: cada caso marcado como Pasa/Falla con evidencia (captura de pantalla o respuesta del API); bugs encontrados reportados como issues nuevos con pasos de reproducción.

### Pasante 2 — Documentación

**Toda la semana: Issue #7 — ARCHITECTURE.md (primera mitad)**
- Actividad: documentar, con evidencia del código, qué componentes del sistema funcionan realmente en producción (ingesta de datos, chat, dashboards) y su flujo de datos.
- Criterio de aceptación: sección "Arquitectura funcional" completa, con referencias a archivos y endpoints concretos, revisada por Desarrollador 1.

---

## Semana 2 (5–9 de octubre)

### Desarrollador 1

**Lunes–martes: Issue #4 (parte 2) — Tests para `chat_service.py` y `agent_tools_service.py`**
- Actividad: pruebas automatizadas para el flujo de chat, incluyendo el caso donde falla la llamada a Gemini (debe usar la respuesta de respaldo local, no propagar el error).
- Criterio de aceptación: suite en verde; el caso de fallo de Gemini queda cubierto explícitamente.

**Miércoles–viernes: Issue #2 — Soporte de PDF en la carga de archivos (inicio)**
- Actividad: diseñar la extracción de tablas desde PDF (evaluar reutilizar `pdfplumber`, ya presente como dependencia) e integrarla al flujo de `smart-upload`.
- Criterio de aceptación: diseño técnico documentado en el issue antes de empezar a escribir código; prueba de concepto con un PDF de ejemplo extrayendo al menos una tabla correctamente.

### Desarrollador 2

**Lunes–jueves: apoyo en revisión de código y pruebas de regresión de lo entregado en la semana 1**

**Viernes: Issue #9 — Limpieza de código muerto en frontend (inicio)**
- Actividad: identificar y remover hooks y componentes sin ningún uso real (`use-agents.ts`, `use-mobile.ts`, `DataTable`, `FileUploadZone`, entre otros ya identificados).
- Criterio de aceptación: lista de archivos a remover confirmada con Desarrollador 1 antes de eliminar nada (evitar borrar algo que sí se use en un flujo no evidente).

### Pasante 1 — QA/Testing

**Lunes–jueves: Issue #6 — Checklist de pruebas manuales: chat con IA y tableros**
- Actividad: ejecutar casos de prueba sobre preguntas ambiguas al chat, creación de tablero sin datos cargados, actualización de tablero tras borrar una tabla con datos, verificación visual del formato markdown en las respuestas (tablas, listas, negritas).
- Criterio de aceptación: cada caso documentado con resultado; bugs reportados como issues nuevos.

**Viernes: consolidación de bugs encontrados en la semana**
- Actividad: reunión corta con el equipo de desarrollo para priorizar los bugs reportados.

### Pasante 2 — Documentación

**Lunes–martes: Issue #7 — ARCHITECTURE.md (finalización)**
- Actividad: completar la sección de "código muerto / desconectado" y "decisiones de arquitectura pendientes", con la resolución tomada en el Issue #1.
- Criterio de aceptación: documento completo, mergeado a `docs/` en el repositorio.

**Miércoles–viernes: Issue #8 — Diccionario de datos por tipo de negocio (inicio)**
- Actividad: documentar, para ferretería y servicios, cada tabla, sus columnas y qué valores son válidos en cada una.
- Criterio de aceptación: al menos 2 de los 3 tipos de negocio completamente documentados.

---

## Semana 3 (12–16 de octubre)

### Desarrollador 1

**Lunes–miércoles: Issue #2 — Soporte de PDF (finalización)**
- Actividad: completar la integración de extracción de PDF con `smart-upload`, manejo de errores cuando el PDF no tiene tablas reconocibles.
- Criterio de aceptación: subir un PDF con una tabla de datos carga correctamente los registros en la tabla correspondiente, igual que hoy funciona con CSV/Excel.

**Jueves–viernes: buffer para bugs críticos reportados por QA + revisión final de Pull Requests pendientes**

### Desarrollador 2

**Lunes–miércoles: Issue #9 — Limpieza de código muerto (finalización)**
- Actividad: remover los archivos confirmados en la semana 2, verificar que el build y los tests siguen pasando.
- Criterio de aceptación: build de producción exitoso tras la limpieza; cero regresiones en la suite de tests.

**Jueves–viernes: buffer para bugs no críticos + apoyo a Desarrollador 1**

### Pasante 1 — QA/Testing

**Lunes–miércoles: regresión completa**
- Actividad: repetir los checklists de las semanas 1 y 2 sobre la versión final del sprint, para confirmar que ningún cambio nuevo rompió algo que antes funcionaba.
- Criterio de aceptación: checklist completo sin fallas nuevas; cualquier hallazgo reportado de inmediato al equipo de desarrollo (prioridad alta dado el cierre de sprint).

**Jueves–viernes: reporte final de QA**
- Actividad: documento resumen de todo lo probado en las 3 semanas, bugs encontrados y su estado (corregido/pendiente).

### Pasante 2 — Documentación

**Lunes–miércoles: Issue #8 — Diccionario de datos (finalización)**
- Actividad: completar el tercer tipo de negocio (restaurante) pendiente de la semana 2.
- Criterio de aceptación: los 3 tipos de negocio completamente documentados.

**Jueves–viernes: consolidación final de toda la documentación del sprint**
- Actividad: revisar que `docs/ARCHITECTURE.md`, el diccionario de datos, y este mismo plan de trabajo reflejen el estado real al cierre del sprint (16 de octubre).
- Criterio de aceptación: documentación entregada y enlazada desde el `README.md` del repositorio.

---

## Seguimiento

Todas las tareas descritas corresponden a issues numerados del 1 al 10 en el repositorio de GitHub (`NiceIam/ucompensar-dashboard-gestion`). El estado de avance día a día se sigue ahí, no en este documento — este documento es el plan; GitHub Issues es el estado real y actualizado.
