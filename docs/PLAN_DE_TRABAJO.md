# Plan de Trabajo y Cronograma — PI0320251

**Proyecto**: Solución WEB para la gestión estratégica de datos con IA
**Código**: PI0320251 — Fundación Universitaria Ucompensar
**Última actualización**: 27 de septiembre de 2026

## Equipo

| Rol | Responsabilidad principal |
|---|---|
| Desarrollador 1 (semillerista, líder técnico) | Arquitectura, backend, seguridad, decisiones técnicas de mayor riesgo |
| Desarrollador 2 (semillerista) | Frontend, features de apoyo, revisión de código |
| Pasante 1 — QA / Testing | Diseño y ejecución de pruebas formales, automatización de pruebas de regresión |
| Pasante 2 — Documentación | Documentación técnica completa del sistema |

**Nota sobre la atribución en Fase 1**: los pasantes de QA y documentación se incorporan formalmente al proyecto en la Fase 2 (sprint final). No se les atribuye trabajo de construcción del sistema en la Fase 1 porque, en ese momento, el software que iban a probar y documentar todavía no existía — atribuirles tareas de desarrollo ahí sería inexacto. Su aporte real y verificable empieza cuando hay features concretas sobre las cuales probar y documentar, que es exactamente el enfoque de la Fase 2.

---

# Fase 1 — Desarrollo base (3 de agosto – 25 de septiembre de 2026)

Trabajo realizado sobre la base de código existente del proyecto, por los 2 desarrolladores, en orden de dependencia técnica.

## Semana 1 (3–7 de agosto): Arquitectura y modelo de datos
**Responsable: Desarrollador 1**

- Diseño de la arquitectura multi-tenant: una base de datos PostgreSQL dedicada por organización (`org_<uuid>`), separada de una base de datos principal (`pi_main`) para metadatos globales.
- Definición del esquema de `pi_main`: tablas `organizations`, `users`, `business_types`.
- Definición del esquema base replicado en cada base de datos de organización: `org_data_tables`, `org_data_rows`, `uploaded_files`, `etl_jobs`, `agent_sessions`, `agent_results`, `chat_messages`, `dashboards`, `widgets`.
- Configuración de pools de conexión asíncronos (asyncpg): un pool para la base principal (2-10 conexiones), pools independientes por organización (1-5 conexiones), creados bajo demanda.
- **Entregable**: `backend/app/database.py` con la lógica de inicialización de esquema y creación dinámica de bases de datos por organización.

## Semana 2 (10–14 de agosto): Autenticación y registro
**Responsable: Desarrollador 1**

- Implementación de autenticación JWT local (algoritmo HS256), sin dependencia de proveedores externos de auth.
- Endpoints: `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`.
- Tokens entregados como cookies HttpOnly (access_token: 60 min; refresh_token: 7 días), nunca expuestos a JavaScript del cliente.
- Rate limiting por endpoint: 5 solicitudes/minuto en registro, 10/minuto en login, 30/minuto en renovación de token.
- Hashing de contraseñas con bcrypt (12 rondas) y denylist de tokens revocados en logout.
- **Entregable**: `backend/app/routers/auth_router.py`, `backend/app/services/auth_service.py`, `backend/app/auth.py`.

## Semana 3 (17–21 de agosto): Tipos de negocio y esquemas por industria
**Responsable: Desarrollador 2** (revisión de Desarrollador 1)

- Definición de 3 tipos de negocio soportados: ferretería, servicios, restaurante, cada uno con su propio esquema de tablas (ej. ferretería: productos, ventas, proveedores, inventario_movimientos).
- Flujo de registro en 3 pasos: datos de cuenta → selección de tipo de negocio → confirmación.
- Endpoint `POST /api/v1/templates/initialize`, que asocia el tipo de negocio elegido a la organización y crea las tablas correspondientes.
- **Entregable**: `backend/app/services/template_service.py`, componente `BusinessTypeSelector` en frontend.

## Semana 4 (24–28 de agosto): Motor de carga inteligente de archivos
**Responsable: Desarrollador 1**

- Desarrollo de `schema_agent_service.py`: análisis automático de columnas de un archivo CSV/Excel/JSON, inferencia de tipo de dato por columna, comparación por similitud de texto contra columnas de tablas ya existentes.
- Creación automática de tabla nueva cuando no hay coincidencia suficiente.
- Endpoint `POST /api/v1/schema/smart-upload`. Diseño deliberado sin uso de modelos de lenguaje en esta ruta (matching determinístico), para mantener costos y latencia bajos.
- **Entregable**: pipeline de ingesta de datos funcional para CSV, Excel y JSON.

## Semana 5 (31 de agosto – 4 de septiembre): Interfaz de usuario base
**Responsable: Desarrollador 2**

- Configuración de Next.js 14 (App Router), TypeScript, Tailwind CSS y shadcn/ui.
- Páginas de autenticación (login, registro de 3 pasos) y middleware de protección de rutas.
- Cliente HTTP centralizado (`lib/api.ts`) con renovación automática de sesión ante un 401.
- **Entregable**: `frontend/src/app/(auth)/*`, `frontend/src/middleware.ts`, `frontend/src/lib/api.ts`.

## Semana 6 (7–11 de septiembre): Generación automática de dashboards
**Responsable: Desarrollador 1 (backend) y Desarrollador 2 (frontend)**

- Desarrollador 1: `dashboard_script_service.py` — generación heurística de visualizaciones (texto+número → barras, fecha+número → línea, categorías → pie), generación de un script Python descargable por tablero.
- Desarrollador 2: renderizado de gráficas con Recharts, páginas de listado y detalle de tableros.
- **Entregable**: `frontend/src/app/(dashboard)/dashboards/*`, `frontend/src/components/charts/chart-renderer.tsx`, `backend/app/services/dashboard_script_service.py`.

## Semana 7 (14–18 de septiembre): Asistente conversacional con IA
**Responsable: Desarrollador 1 (backend/IA) y Desarrollador 2 (frontend)**

- Desarrollador 1: integración con Google Gemini vía `google-genai`; construcción de contexto inyectando datos reales de la organización en el prompt (`agent_tools_service.py`).
- Desarrollador 2: componente de chat flotante con soporte de formato enriquecido (negritas, listas, tablas, encabezados) y respuesta local de respaldo cuando no hay IA disponible.
- **Entregable**: `frontend/src/components/chat/floating-chat.tsx`, `backend/app/services/agent_tools_service.py`, `backend/app/services/chat_service.py`.

## Semana 8 (21–25 de septiembre): Estabilización, corrección de errores y despliegue a producción
**Responsable: Desarrollador 1 y Desarrollador 2 (trabajo conjunto)**

- Auditoría completa del sistema y corrección de 5 errores críticos: eliminación de tabla que fallaba siempre por uso indebido de `RETURNING` con función de agregación; filas duplicadas en metadata de tablas por falta de restricción de unicidad; condición de carrera al crear tablas; carga de archivos sin transacción; token de sesión que no se revocaba al rotarlo.
- Actualización de dependencias críticas: `google-adk` 0.3.0 → 2.9.2; retiro de `google-generativeai` (sin soporte oficial) en favor de `google-genai`; actualización del modelo de Gemini (el anterior fue dado de baja por Google) a `gemini-3.6-flash`.
- Inicialización de control de versiones (Git) y repositorio remoto en GitHub.
- Despliegue en producción: backend y frontend en Vercel (proyectos separados), base de datos en Neon; corrección de compatibilidad SSL y de política de cookies entre dominios distintos.
- Configuración de tablero de seguimiento (GitHub Issues + Projects) con el backlog inicial.
- **Entregable**: sistema desplegado y accesible públicamente; backlog documentado (10 tareas).

---

# Fase 2 — Sprint final (28 de septiembre – 16 de octubre de 2026)

Este sprint tiene tres frentes que avanzan **en paralelo sobre las mismas features, semana a semana**: desarrollo, pruebas formales, y documentación. Ninguno de los tres es independiente de los otros — cada semana, QA prueba lo que Desarrollo entregó esa semana (o la anterior), y Documentación redacta sobre lo mismo.

## Documentos que produce el Pasante de Documentación

Ninguno de estos existe hoy en el proyecto. No es "una arquitectura .md" aislada — son 8 documentos técnicos independientes, cada uno con un propósito distinto, repartidos a lo largo de las 3 semanas:

| # | Documento | Contenido |
|---|---|---|
| 1 | `docs/ARCHITECTURE.md` | Arquitectura real del sistema: qué componentes funcionan en producción, flujo de datos, qué está desconectado o pendiente de decisión |
| 2 | `docs/API.md` | Referencia completa de la API: cada endpoint, sus parámetros, respuestas, códigos de error, con ejemplos reales de solicitud/respuesta |
| 3 | `docs/DATABASE.md` | Diccionario de datos completo: esquema de `pi_main` y de cada tipo de negocio, con tipo de dato y validez de cada columna |
| 4 | `docs/SECURITY.md` | Modelo de seguridad: manejo de JWT, rate limiting, denylist de tokens, política de cookies, y los 5 hallazgos corregidos en la Fase 1 |
| 5 | `docs/DEPLOYMENT.md` | Runbook de despliegue: variables de entorno, pasos para desplegar en Vercel/Neon, procedimiento de rollback, troubleshooting de problemas ya conocidos (SSL, CORS, SameSite) |
| 6 | `docs/DECISIONS.md` | Registro de decisiones de arquitectura (formato ADR): por qué una base de datos por organización y no un esquema compartido, por qué matching determinístico y no un LLM en la carga de archivos, y las decisiones que queden pendientes durante el sprint |
| 7 | `docs/MANUAL_USUARIO.md` | Guía para el usuario final (el administrador de la PYME): cómo registrarse, subir datos, leer un tablero, usar el chat |
| 8 | `docs/GLOSARIO.md` | Términos del dominio del proyecto (multi-tenant, tipo de negocio, matching de columnas, etc.) para que cualquier lector nuevo del proyecto no dependa de adivinar |

## Metodología de pruebas del Pasante de QA

No son checklists sueltos. Cada caso de prueba se documenta en `docs/testing/` con este formato mínimo:

```
ID: TC-XXX
Feature: [a qué funcionalidad pertenece]
Precondición: [estado necesario antes de ejecutar la prueba]
Pasos: [numerados, reproducibles por cualquier persona]
Resultado esperado: [qué debe pasar]
Resultado obtenido: [Pasa / Falla + evidencia]
Severidad si falla: [Crítica / Alta / Media / Baja]
```

Además de pruebas manuales documentadas, el pasante contribuye **pruebas automatizadas reales** usando la infraestructura que el proyecto ya tiene configurada (Playwright para frontend, pytest para backend) — no solo verificación manual repetitiva. Esto es lo que distingue un plan de pruebas de nivel de tesis de una simple lista de verificación.

---

## Semana 1 (28 de septiembre – 2 de octubre)

**Tema de la semana: estabilidad de la base (multi-tenancy, autenticación, carga de archivos)**

### Desarrollador 1

- **Lunes–martes — Issue #1**: decisión sobre el pipeline de IA de insights automáticos (reconectar o eliminar), documentada en el issue.
- **Miércoles–viernes — Issue #4 (parte 1)**: pruebas automatizadas para `schema_agent_service.py` (creación de tablas, carga de CSV).

### Desarrollador 2

- **Lunes (primera hora) — Issue #10**: rotar contraseña de Neon y actualizar variable en Vercel.
- **Martes–jueves — Issue #3**: corregir el mapeo roto de sector → tipo de negocio en el registro.
- **Viernes**: revisión de código de Desarrollador 1.

### Pasante 1 — QA/Testing

- **Lunes–martes**: redactar `docs/testing/PLAN_DE_PRUEBAS.md` (metodología, alcance, formato de caso de prueba) — este documento define cómo se van a probar TODAS las features del sprint, no solo esta semana.
- **Miércoles–jueves**: escribir y ejecutar casos de prueba formales (TC-001 a TC-010 aprox.) para: registro de organización con los 3 tipos de negocio, y la corrección del Issue #3 que entrega Desarrollador 2 — confirmar que ya no se generan tablas duplicadas.
- **Viernes**: escribir la primera prueba automatizada en Playwright (`frontend/e2e/`) que cubra el flujo completo de registro, para que quede como prueba de regresión permanente (no solo un checklist manual que se vuelve a hacer a mano cada vez).

### Pasante 2 — Documentación

- **Lunes–miércoles**: `docs/DATABASE.md` — diccionario de datos completo de los 3 tipos de negocio (ferretería, servicios, restaurante), documentando el esquema real verificado contra la base de datos, no contra la memoria de lo que "debería" ser.
- **Jueves–viernes**: `docs/SECURITY.md` — documentar el modelo de autenticación/JWT y los 5 errores de seguridad corregidos en la Fase 1 (con causa raíz de cada uno).

---

## Semana 2 (5–9 de octubre)

**Tema de la semana: chat con IA, dashboards, y una feature nueva (PDF)**

### Desarrollador 1

- **Lunes–martes — Issue #4 (parte 2)**: pruebas automatizadas para `chat_service.py` y `agent_tools_service.py`, incluyendo el caso donde falla Gemini (debe usar respuesta local, no romper).
- **Miércoles–viernes — Issue #2 (inicio)**: diseño e implementación de extracción de tablas desde PDF, integrada a `smart-upload`.

### Desarrollador 2

- **Lunes–jueves**: pruebas de regresión y corrección de bugs reportados por QA en la semana 1.
- **Viernes — Issue #9 (inicio)**: identificar, con Desarrollador 1, qué hooks y componentes de frontend no tienen ningún uso real.

### Pasante 1 — QA/Testing

- **Lunes–miércoles**: casos de prueba formales (TC-011 a TC-025 aprox.) para el chat con IA (preguntas ambiguas, verificación de formato markdown en las respuestas) y para la generación de dashboards (tablero sin datos, actualización tras borrar una tabla).
- **Jueves**: casos de prueba para la extracción de PDF que entrega Desarrollador 1 esta semana — incluir al menos un PDF mal formado como caso negativo.
- **Viernes**: segunda prueba automatizada en Playwright cubriendo el flujo de chat, y reporte semanal de bugs con severidad asignada.

### Pasante 2 — Documentación

- **Lunes–martes**: `docs/API.md` — referencia completa de los endpoints de chat, dashboards y schema, con ejemplos reales de solicitud/respuesta (tomados de pruebas contra el entorno de producción).
- **Miércoles–viernes**: `docs/ARCHITECTURE.md` — mapa completo de qué funciona en producción, qué está desconectado, y la resolución tomada en el Issue #1.

---

## Semana 3 (12–16 de octubre)

**Tema de la semana: cierre, regresión completa, y consolidación**

### Desarrollador 1

- **Lunes–miércoles — Issue #2 (finalización)**: completar soporte de PDF, manejo de errores cuando no hay tablas reconocibles.
- **Jueves–viernes**: corrección de bugs críticos reportados por QA durante la regresión final; revisión de todos los Pull Requests pendientes del sprint.

### Desarrollador 2

- **Lunes–miércoles — Issue #9 (finalización)**: remover el código muerto identificado, confirmar build y tests en verde.
- **Jueves–viernes**: apoyo a Desarrollador 1 en corrección de bugs de última hora.

### Pasante 1 — QA/Testing

- **Lunes–miércoles**: regresión completa — reejecutar TODOS los casos de prueba de las semanas 1 y 2 sobre la versión final del sprint, más casos nuevos para el soporte de PDF terminado.
- **Jueves**: tercera prueba automatizada en Playwright (regresión de multi-tenancy: dos organizaciones no pueden ver datos una de la otra) y ampliar la suite de pytest del backend para los módulos identificados sin cobertura (`schema_agent_service.py`, `chat_service.py`).
- **Viernes**: `docs/testing/REPORTE_FINAL_QA.md` — resumen ejecutivo de las 3 semanas: casos ejecutados, bugs encontrados, bugs corregidos, bugs que quedan pendientes y su severidad.

### Pasante 2 — Documentación

- **Lunes–martes**: `docs/DEPLOYMENT.md` (runbook de despliegue) y `docs/DECISIONS.md` (decisiones de arquitectura clave del proyecto, formato ADR).
- **Miércoles**: `docs/MANUAL_USUARIO.md` y `docs/GLOSARIO.md`.
- **Jueves–viernes**: consolidación final — revisar los 8 documentos entregados durante el sprint, verificar que estén enlazados desde el `README.md`, y que reflejen el estado real del sistema al 16 de octubre (no lo que se planeó, sino lo que efectivamente quedó construido).

---

## Seguimiento

El estado de avance día a día se sigue en GitHub Issues (`NiceIam/ucompensar-dashboard-gestion`), no en este documento — este documento es el plan; GitHub Issues es el estado real y actualizado. Los 8 documentos de esta fase y los casos de prueba formales quedan en `docs/` como entregables permanentes del proyecto, no solo como evidencia de que se trabajó.
