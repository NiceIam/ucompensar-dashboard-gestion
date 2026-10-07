# Referencia de la API — Chat, Tableros y Schema

**Responsable**: Pasante 2 — Documentación
**Sprint**: 2 (5–9 de octubre de 2026)
**Versión del código**: `main` @ `8ba65d7` (backend sin cambios desde `a90a67c`)
**Fuente de los ejemplos**: solicitudes reales ejecutadas el 6 de octubre de 2026 contra el backend en **entorno local** (PostgreSQL 15 en Docker), con una organización de prueba de tipo Ferretería y los archivos de `test-data/ferreteria/`

> **Pendiente de validar en producción**: el plan del sprint pide tomar los ejemplos del entorno de producción. Se usaron ejemplos locales porque varios endpoints crean, modifican o eliminan datos (tablas, filas, tableros), y hacerlo en producción requiere autorización del equipo y una organización de prueba dedicada. El código es el mismo, así que las respuestas deben coincidir. Las únicas diferencias esperadas son los identificadores, las fechas y la respuesta del chat, que en producción sí tiene `GOOGLE_API_KEY`.

Este documento cubre los tres grupos de endpoints del Sprint 2: **chat con IA**, **tableros (dashboards)** y **schema** (tablas lógicas y carga inteligente). La autenticación está documentada en `docs/SECURITY.md` y el modelo de datos en `docs/DATABASE.md`.

---

## 1. Convenciones generales

### 1.1 URL base y documentación interactiva

| Entorno | URL base | Swagger |
|---|---|---|
| Local | `http://localhost:8000` | `http://localhost:8000/docs` |
| Producción | URL del proyecto de backend en Vercel | Deshabilitado (`APP_ENV=production`) |

### 1.2 Autenticación

Todos los endpoints de este documento requieren sesión. El token se envía **solo** en la cookie HttpOnly `access_token`, que fija `POST /api/v1/auth/login`. El header `Authorization: Bearer` no se acepta.

- Desde el navegador: `fetch(url, { credentials: "include" })`.
- Desde `curl`: iniciar sesión con `-c cookies.txt` y reutilizar con `-b cookies.txt`.

```bash
curl -c cookies.txt -H "Content-Type: application/json" -d '{"email":"usuario@example.com","password":"********"}' http://localhost:8000/api/v1/auth/login
```

Sin cookie, o con la cookie vencida, la respuesta es:

```json
HTTP 401
{ "detail": "No autenticado." }
```

Todo endpoint opera **solo sobre la organización del usuario autenticado**: el `org_id` sale del token, nunca de la URL ni del cuerpo.

### 1.3 Formato de errores

| Código | Cuándo | Forma de `detail` |
|---|---|---|
| 400 | Regla de negocio | Texto: `{"detail": "..."}` |
| 401 | Sin sesión o token inválido | Texto |
| 404 | Recurso inexistente en la organización | Texto, ej. `{"detail": "Tabla no encontrada"}` |
| 409 | Conflicto (tabla duplicada) | Texto |
| 422 | Cuerpo inválido (validación de FastAPI/Pydantic) | **Lista** de errores: `{"detail": [{"type", "loc", "msg", "input"}]}` |
| 500 | Error no controlado | Texto plano `Internal Server Error` (no JSON) |

Ejemplo de 422 real (falta el campo `name` al crear un tablero):

```json
{
  "detail": [
    { "type": "missing", "loc": ["body", "name"], "msg": "Field required", "input": { "description": "sin nombre" } }
  ]
}
```

### 1.4 Identificadores

Todos los IDs (`dashboard_id`, `widget_id`, `table_id`, `row_id`, `message_id`) son **UUID v4**. Ver el hallazgo A-01: algunos endpoints responden 500 si el ID no tiene formato UUID.

---

## 2. Resumen de endpoints

La columna **Frontend** indica si la interfaz actual llama al endpoint (búsqueda en `frontend/src`).

| Método | Ruta | Descripción | Frontend |
|---|---|---|---|
| POST | `/api/v1/chat/message` | Envía una pregunta al asistente | Sí |
| POST | `/api/v1/chat/upload` | Sube un archivo desde el chat y lo carga | Sí |
| GET | `/api/v1/chat/history` | Historial de mensajes de la organización | Sí |
| POST | `/api/v1/dashboards` | Crea un tablero (y su script) | Sí |
| GET | `/api/v1/dashboards` | Lista tableros | Sí |
| GET | `/api/v1/dashboards/{dashboard_id}` | Detalle con widgets | Sí |
| PUT | `/api/v1/dashboards/{dashboard_id}` | Reemplaza nombre, descripción y visibilidad | No |
| PATCH | `/api/v1/dashboards/{dashboard_id}` | Actualización parcial | No |
| DELETE | `/api/v1/dashboards/{dashboard_id}` | Borrado lógico | Sí |
| POST | `/api/v1/dashboards/{dashboard_id}/widgets` | Agrega un widget | No |
| PUT | `/api/v1/dashboards/{dashboard_id}/widgets/{widget_id}` | Reemplaza un widget | Sí |
| PATCH | `/api/v1/dashboards/{dashboard_id}/widgets/{widget_id}` | Actualiza un widget (posición, tamaño…) | No |
| DELETE | `/api/v1/dashboards/{dashboard_id}/widgets/{widget_id}` | Elimina un widget | No |
| GET | `/api/v1/dashboards/{dashboard_id}/script` | Script Python del tablero | Sí |
| GET | `/api/v1/dashboards/{dashboard_id}/script/download` | Descarga el script como `.py` | Sí |
| PUT | `/api/v1/dashboards/{dashboard_id}/script` | Reemplaza el script | No |
| POST | `/api/v1/dashboards/{dashboard_id}/execute` | Gráficas y KPIs del tablero | Sí |
| POST | `/api/v1/schema/analyze` | Analiza un archivo sin cargarlo | No |
| POST | `/api/v1/schema/smart-upload` | Analiza, decide la tabla y carga | Sí |
| POST | `/api/v1/schema/tables` | Crea una tabla lógica | No |
| PUT | `/api/v1/schema/tables/{table_id}` | Agrega columnas o renombra | Sí |
| DELETE | `/api/v1/schema/tables/{table_id}` | Elimina una tabla y sus filas | Sí |
| GET | `/api/v1/schema/tables/{table_id}/rows` | Filas paginadas | Sí |
| DELETE | `/api/v1/schema/tables/{table_id}/rows/{row_id}` | Elimina una fila | Sí |
| GET | `/api/v1/schema/tables/{table_id}/template` | Plantilla CSV de la tabla | Sí |
| GET | `/api/v1/schema/template-all` | Plantilla Excel con todas las tablas | Sí |
| GET | `/api/v1/schema/tables/{table_id}/export` | Exporta los datos como CSV | Sí |

---

## 3. Chat con IA

Router: `backend/app/routers/chat.py` · Servicios: `chat_service.py`, `agent_tools_service.py`

### 3.1 `POST /api/v1/chat/message` — enviar una pregunta

**Cuerpo** (`application/json`):

| Campo | Tipo | Requerido | Validación |
|---|---|---|---|
| `content` | string | Sí | 1–4000 caracteres |
| `file_id` | string | No | Se recibe, pero el flujo actual **no lo usa** |

**Qué hace**:
1. Guarda la pregunta en `chat_messages`.
2. Toma los últimos 8 mensajes como historial (Gemini recibe 6).
3. Construye el contexto: nombre de la organización, tablas con sus columnas y conteos, y una muestra de hasta 10 filas de las tablas relacionadas con la pregunta (`query_data`).
4. Llama a Gemini (`GEMINI_MODEL`, temperatura 0.3, máximo 2048 tokens de salida).
5. Si la respuesta trae bloques ` ```chart ` con JSON válido, los extrae y los vuelve a anexar al final del contenido.
6. Guarda y devuelve **solo** el mensaje del asistente.

**Respuesta 200** (`ChatMessageResponse`), ejemplo real **sin** `GOOGLE_API_KEY`:

```json
{
  "message_id": "6f30596c-8d9d-4715-ae34-8488d033a4d7",
  "role": "assistant",
  "content": "Error con Gemini: No API key was provided. Please pass a valid API key. Learn how to create an API key at https://ai.google.dev/gemini-api/docs/api-key.. Usando datos locales.",
  "created_at": "2026-10-07T00:08:55.958659Z"
}
```

> Cuando Gemini falla, el endpoint **no rompe** (responde 200), pero tampoco genera una respuesta con los datos locales, aunque el texto diga "Usando datos locales". Ver el hallazgo A-03.

**Formato de gráficas en `content`**: cuando el asistente genera una gráfica, el contenido termina con un bloque así, que el frontend renderiza con Recharts:

````text
```chart
{"type":"bar","title":"Ventas por producto","data":[{"name":"Cemento Argos 50kg","value":57}],"x":"name","y":"value","color":"#3b82f6"}
```
````

**Errores**: 401 sin sesión; 422 si falta `content` o supera 4000 caracteres:

```json
{ "detail": [{ "type": "missing", "loc": ["body", "content"], "msg": "Field required", "input": { "message": "hola" } }] }
```

### 3.2 `POST /api/v1/chat/upload` — subir un archivo desde el chat

**Cuerpo** (`multipart/form-data`):

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `file` | archivo | Sí | CSV, Excel (`.xlsx`, `.xls`) o JSON |
| `message` | string | No | Texto que acompaña al archivo; si falta se usa "Subiendo archivo: {nombre}" |

```bash
curl -b cookies.txt -F "file=@test-data/ferreteria/proveedores.csv" -F "message=Carga mis proveedores" http://localhost:8000/api/v1/chat/upload
```

Ejecuta el mismo **smart upload** de `/api/v1/schema/smart-upload` (sección 5.2), pero responde con un mensaje de chat en markdown. **Solo procesa la primera hoja** de un Excel; para varias hojas usar `/schema/smart-upload`.

**Respuesta 200** (real):

```json
{
  "message_id": "5e966e55-6442-4b3d-ab0d-7696dab4127b",
  "role": "assistant",
  "content": "**Archivo procesado: proveedores.csv**\n\nAnalice el archivo y encontre que coincide con la tabla existente **proveedores** (coincidencia: 160%).\n\n**Columnas detectadas:** nombre, contacto, telefono, email, direccion, productos_suministrados\n\n**Acciones realizadas:**\n- Cargados 15 registros en 'proveedores'\n\n**Resultado:** 15 registros cargados exitosamente. Total en tabla: 15 registros.",
  "created_at": "2026-10-07T00:08:57.872762Z"
}
```

**Archivo no soportado**: la respuesta sigue siendo **200**, con el error dentro del mensaje. Ejemplo real con un PDF (el selector del chat sí permite elegir `.pdf`):

```json
{
  "role": "assistant",
  "content": "**Error al procesar reporte.pdf**\n\nNo pude procesar el archivo: 422: Tipo de archivo no soportado. Use CSV, Excel o JSON.\n\nAsegurate de que sea un CSV o Excel valido con encabezados en la primera fila."
}
```

### 3.3 `GET /api/v1/chat/history` — historial

| Parámetro (query) | Tipo | Default | Descripción |
|---|---|---|---|
| `limit` | entero | 50 | Máximo 200 |

**Respuesta 200** (`ChatHistoryResponse`), recortada:

```json
{
  "messages": [
    { "message_id": "bfa68191-…", "role": "user", "content": "¿Cuántos productos tengo y cuál es el más caro?", "created_at": "2026-10-07T00:08:54.754538Z" },
    { "message_id": "6f30596c-…", "role": "assistant", "content": "Error con Gemini: …", "created_at": "2026-10-07T00:08:55.958659Z" }
  ],
  "total": 4
}
```

- Los mensajes vienen en orden cronológico ascendente.
- `total` es la cantidad de mensajes **devueltos**, no el total de la organización.
- Devuelve los **primeros** `limit` mensajes, no los últimos. Ver el hallazgo A-02.

---

## 4. Tableros (dashboards)

Router: `backend/app/routers/dashboards.py` · Servicios: `dashboard_service.py`, `dashboard_script_service.py`

### 4.1 Modelos

**`DashboardResponse`**

| Campo | Tipo | Descripción |
|---|---|---|
| `dashboard_id` | UUID | |
| `org_id` | UUID | Organización dueña |
| `name` | string | 2–120 caracteres |
| `description` | string o null | Máximo 500 caracteres |
| `is_public` | boolean | Default `false`; hoy no tiene efecto (no hay vista pública) |
| `created_at`, `updated_at` | datetime ISO 8601 | UTC |

**`DashboardDetail`** = `DashboardResponse` + `widgets: WidgetResponse[]`.

**`WidgetResponse`**

| Campo | Tipo | Validación al crear |
|---|---|---|
| `widget_id`, `dashboard_id` | UUID | |
| `title` | string | 1–120 caracteres |
| `widget_type` | string | Al crear: `bar_chart`, `line_chart`, `pie_chart`, `area_chart`, `radar_chart`, `metric`, `table`, `scatter_chart`, `kpi_card`, `data_table`, `text`. Al actualizar (PATCH) no se valida contra esta lista |
| `config` | objeto | Libre |
| `position_x`, `position_y` | entero | ≥ 0 |
| `width` | entero | 1–12 (grilla de 12 columnas) |
| `height` | entero | ≥ 1 |
| `data_source_query` | objeto o null | Libre |

### 4.2 `POST /api/v1/dashboards` — crear

```json
{ "name": "Ventas del mes", "description": "Tablero de prueba para la documentación" }
```

**Respuesta 201** (real). Además, genera el script Python del tablero (sección 4.7):

```json
{
  "dashboard_id": "5286caaf-f565-451c-b056-994d414770aa",
  "org_id": "493858b1-35aa-4336-8e64-4696e4be75a9",
  "name": "Ventas del mes",
  "description": "Tablero de prueba para la documentación",
  "is_public": false,
  "created_at": "2026-10-07T00:08:53.665273Z",
  "updated_at": "2026-10-07T00:08:53.665273Z"
}
```

### 4.3 `GET /api/v1/dashboards` — listar

**200**: arreglo de `DashboardResponse`. Excluye los tableros eliminados.

### 4.4 `GET /api/v1/dashboards/{dashboard_id}` — detalle

**200**: `DashboardDetail` con sus widgets. **404** si no existe o fue eliminado:

```json
{ "detail": "Dashboard no encontrado." }
```

### 4.5 `PUT` y `PATCH /api/v1/dashboards/{dashboard_id}` — actualizar

- `PUT` exige el cuerpo completo de creación (`name` obligatorio).
- `PATCH` acepta cualquier subconjunto de `name`, `description`, `is_public`.

```json
PATCH { "description": "Descripción actualizada" }
→ 200 { "dashboard_id": "5286caaf-…", "description": "Descripción actualizada", "updated_at": "2026-10-07T00:08:54.160604Z", … }
```

### 4.6 `DELETE /api/v1/dashboards/{dashboard_id}` — eliminar

Borrado lógico (llena `deleted_at`). **200**:

```json
{ "message": "Dashboard eliminado correctamente." }
```

### 4.7 Widgets

| Operación | Cuerpo | Respuesta |
|---|---|---|
| `POST …/widgets` | `WidgetCreate` completo | **201** `WidgetResponse` |
| `PUT …/widgets/{widget_id}` | `WidgetCreate` completo | 200 `WidgetResponse` |
| `PATCH …/widgets/{widget_id}` | Cualquier subconjunto (pensado para arrastrar y soltar) | 200 `WidgetResponse` |
| `DELETE …/widgets/{widget_id}` | — | 200 `{"message": "Widget eliminado correctamente."}` |

Ejemplo real de creación:

```json
POST /api/v1/dashboards/5286caaf-…/widgets
{ "title": "Ventas por producto", "widget_type": "bar_chart", "config": { "table": "ventas", "x": "producto", "y": "total" }, "position_x": 0, "position_y": 0, "width": 6, "height": 4 }

→ 201
{
  "widget_id": "1f1f0e58-55f6-482d-97fe-1bdc092f43f1",
  "dashboard_id": "5286caaf-f565-451c-b056-994d414770aa",
  "title": "Ventas por producto",
  "widget_type": "bar_chart",
  "config": { "x": "producto", "y": "total", "table": "ventas" },
  "position_x": 0, "position_y": 0, "width": 6, "height": 4,
  "data_source_query": null,
  "created_at": "2026-10-07T00:08:53.926827Z",
  "updated_at": "2026-10-07T00:08:53.926827Z"
}
```

> Los widgets se guardan, pero **no determinan** lo que muestra el tablero: las gráficas salen de `/execute` (sección 4.9), que no lee los widgets.

### 4.8 Script Python del tablero

| Endpoint | Respuesta |
|---|---|
| `GET …/script` | 200 `{"script": "<código>", "dashboard_id": "…"}`. Si no existe, lo genera |
| `GET …/script/download` | 200 `text/x-python`, con `Content-Disposition: attachment; filename="dashboard_5286caaf.py"` |
| `PUT …/script` | `multipart/form-data` con `file`. 200 `{"message": "Script actualizado", "size": 46}` |

El script se guarda en disco en `backend/dashboard_scripts/<org_id>/<dashboard_id>.py`. Inicio real del script generado:

```python
"""
Dashboard: Ventas del mes
Generado automaticamente por el sistema.
Edita este archivo para personalizar los graficos y KPIs.

Funciones disponibles:
  query(sql) -> list[dict]   Ejecuta SQL en la BD de tu empresa
...
"""
```

> **Importante**: el script **nunca se ejecuta**. Ni el `query(sql)` que anuncia su encabezado ni los cambios subidos con `PUT …/script` tienen efecto sobre el tablero. Ver el hallazgo A-04.

### 4.9 `POST /api/v1/dashboards/{dashboard_id}/execute` — gráficas y KPIs

Sin cuerpo. Devuelve los datos que el frontend dibuja con Recharts. Se calculan **siempre igual**, a partir de todas las tablas lógicas de la organización (hasta 500 filas por tabla):

| Regla | Gráfica |
|---|---|
| Tabla con columna de texto y columna numérica | Barras: suma de la primera numérica por la primera de texto (top 15) |
| Tabla con columna de texto y más de 1 fila | Torta: conteo por la primera de texto (top 10) |
| Tabla con columna de fecha y columna numérica | Línea: suma por mes (`YYYY-MM`), si hay más de 1 mes |
| Cada tabla | KPI "Total {tabla}" con su número de filas, más un KPI inicial "Registros totales" |

**Respuesta 200** (real, recortada):

```json
{
  "charts": [
    {
      "type": "bar",
      "title": "Ventas por producto",
      "data": [{ "name": "Cable THW 12 AWG (metro)", "value": 150 }, { "name": "Cemento Argos 50kg", "value": 57 }],
      "x": "name", "y": "value", "color": "#3b82f6"
    }
  ],
  "kpis": [
    { "label": "Registros totales", "value": 69, "icon": "TrendingUp" },
    { "label": "Total Servicios", "value": 0, "icon": "Database" }
  ]
}
```

En el ejemplo, la organización es de tipo Ferretería y aun así aparece el KPI "Total Servicios": es el efecto del Issue #3 (ver `docs/DATABASE.md`).

---

## 5. Schema (tablas lógicas y carga inteligente)

Router: `backend/app/routers/schema.py` · Servicio: `schema_agent_service.py`. Las "tablas" son tablas lógicas guardadas en `org_data_tables` y `org_data_rows` (ver `docs/DATABASE.md`).

**Formatos de archivo aceptados**: CSV, Excel (`.xlsx`, `.xls`) y JSON. **PDF no está soportado** (Issue #2).

### 5.1 `POST /api/v1/schema/analyze` — analizar sin cargar

`multipart/form-data` con `file`. No modifica datos.

**Respuesta 200** (real, recortada a una columna):

```json
{
  "row_count": 30,
  "column_count": 7,
  "columns": [
    {
      "original_name": "nombre", "clean_name": "nombre", "inferred_type": "text",
      "non_null_count": 30, "total_count": 30, "null_count": 0, "unique_count": 30,
      "sample_values": ["Martillo Stanley 16oz", "Destornillador Phillips 1/4", "Taladro Percutor Bosch 13mm"],
      "is_required": true
    }
  ],
  "matching_table": {
    "table_id": "df95785b-…", "table_name": "productos", "display_name": "Productos",
    "match_score": 1.7, "matched_columns": ["nombre", "categoria", "…"], "missing_in_table": [], "extra_in_table": []
  }
}
```

### 5.2 `POST /api/v1/schema/smart-upload` — analizar, decidir y cargar

`multipart/form-data` con `file`. Es la carga que usa la pantalla "Mis Datos".

1. Analiza las columnas e infiere sus tipos.
2. Busca la tabla más parecida (puntaje ≥ 0.3).
3. Si la encuentra, **carga ahí** (agregando columnas nuevas si hace falta); si no, **crea** una tabla nueva.
4. Inserta las filas en una transacción (todo o nada).

**Respuesta 200** con una hoja (real, recortada):

```json
{
  "status": "loaded_to_existing",
  "table_name": "productos",
  "table_id": "df95785b-8ed8-46c5-b5b6-0822d17b92a9",
  "match_score": 1.7,
  "rows_inserted": 30,
  "total_rows": 30,
  "actions": [{ "action": "load_data", "detail": "Cargados 30 registros en 'productos'" }],
  "analysis": { "row_count": 30, "column_count": 7, "columns": ["…"] }
}
```

**Respuesta 200 con un Excel de varias hojas** (ejemplo **ilustrativo**, construido a partir del código de `schema.py` y no de una ejecución real): cada hoja se procesa por separado (en serie) y una hoja vacía se omite:

```json
{
  "status": "multi_sheet_processed",
  "multi_sheet": true,
  "sheets_processed": 3,
  "total_rows_inserted": 85,
  "sheets": [
    { "sheet_name": "Productos", "status": "loaded_to_existing", "rows_inserted": 30, "…": "…" },
    { "sheet_name": "Notas", "status": "skipped_empty", "rows_inserted": 0 },
    { "sheet_name": "Ventas", "status": "error", "error": "…", "rows_inserted": 0 }
  ]
}
```

> `match_score` puede ser **mayor que 1**: suma la proporción de columnas coincidentes más 0.1 por cada par de nombres similares. El chat lo muestra como porcentaje ("coincidencia: 160%"). Ver el hallazgo A-06.

### 5.3 `POST /api/v1/schema/tables` — crear tabla

```json
{
  "table_name": "garantias",
  "display_name": "Garantías",
  "columns": [{ "name": "marca", "type": "text" }, { "name": "garantia_meses", "type": "integer" }]
}
```

| Campo | Validación |
|---|---|
| `table_name` | 1–100 caracteres. Único por organización |
| `display_name` | 1–150 caracteres |
| `columns` | Lista de `{name, type, required?}`; tipos: `text`, `number`, `integer`, `date`, `boolean` (no se valida) |

**200** (real):

```json
{ "table_id": "777826fb-2b7e-4dd9-9735-1526eadcadbc", "table_name": "garantias", "display_name": "Garantías",
  "columns": [{ "name": "marca", "type": "text" }, { "name": "garantia_meses", "type": "integer" }], "row_count": 0 }
```

**409** si ya existe: `{"detail": "La tabla 'garantias' ya existe"}`

> Responde **200**, no 201, aunque crea un recurso.

### 5.4 `PUT /api/v1/schema/tables/{table_id}` — agregar columnas o renombrar

```json
{ "add_columns": [{ "name": "proveedor", "type": "text" }], "new_display_name": "Garantías de productos" }
```

**200** (real): `{"table_id": "777826fb-…", "table_name": "garantias", "display_name": "Garantías de productos", "columns": [ …3 columnas… ], "columns_added": 1}`. **404** si la tabla no existe. No permite quitar ni renombrar columnas.

### 5.5 `DELETE /api/v1/schema/tables/{table_id}` — eliminar tabla

**200**: `{"table_name": "garantias", "display_name": "Garantías de productos", "rows_deleted": 0}`. Elimina también todas sus filas. **404** si no existe.

### 5.6 `GET /api/v1/schema/tables/{table_id}/rows` — filas

| Parámetro (query) | Default | Descripción |
|---|---|---|
| `limit` | 20 | Máximo 100 |
| `offset` | 0 | Desplazamiento |

Orden: más recientes primero (`created_at DESC`).

**200** (real, `limit=2`):

```json
{
  "table_name": "productos",
  "display_name": "Productos",
  "total": 30,
  "rows": [
    {
      "id": "06080072-9d6f-43f0-a3ea-b1cded40bb84",
      "data": { "stock": 120, "codigo": "HM-002", "nombre": "Destornillador Phillips 1/4", "categoria": "Herramientas manuales",
                "proveedor": "Ferreimportaciones", "precio_venta": 14500, "precio_compra": 8500 },
      "created_at": "2026-10-07T00:08:41.507393+00:00"
    }
  ]
}
```

**404** `{"detail": "Tabla no encontrada"}` si el UUID no existe; **500** si el ID no es un UUID (A-01).

### 5.7 `DELETE /api/v1/schema/tables/{table_id}/rows/{row_id}` — eliminar fila

**200** (real): `{"deleted": true, "new_count": 29}`. Si la fila no existe, responde igual (200, `deleted: true`) sin borrar nada.

### 5.8 Plantillas y exportación

| Endpoint | Tipo de respuesta | Nombre de archivo |
|---|---|---|
| `GET /tables/{table_id}/template` | `text/csv`: encabezados y una fila de ejemplo según el tipo | `plantilla_<tabla>.csv` |
| `GET /template-all` | Excel `.xlsx`: una hoja por tabla, encabezados en negrita con el tipo como comentario | `plantilla_completa.xlsx` |
| `GET /tables/{table_id}/export` | `text/csv` con todas las filas (solo las columnas definidas) | `<tabla>_datos.csv` |

Plantilla real de `productos`:

```text
nombre,categoria,precio_compra,precio_venta,stock,proveedor,codigo
ejemplo_texto,ejemplo_texto,0.00,0.00,0,ejemplo_texto,ejemplo_texto
```

`template-all` responde **404** `{"detail": "No hay tablas configuradas"}` si la organización no tiene tablas.

---

## 6. Hallazgos para el equipo de Desarrollo

Comportamientos observados al ejecutar los ejemplos. Se documentan para que el lector de la API no se sorprenda; la corrección corresponde a Desarrollo.

| ID | Hallazgo | Evidencia | Impacto | Relación |
|---|---|---|---|---|
| A-01 | Un `table_id` que no es UUID produce **500** en `/schema/tables/{id}/…` (`uuid.UUID()` sin manejo de error) | `GET /schema/tables/no-es-uuid/rows` → 500 `Internal Server Error` | Error no controlado; debería ser 404 o 422 | Bug |
| A-02 | `/chat/history` usa `ORDER BY created_at ASC LIMIT n`: devuelve los **primeros** n mensajes | Con 6 mensajes, `limit=4` devolvió los 4 más antiguos | Pasados 50 mensajes, los nuevos dejan de aparecer al recargar el chat | Bug visible al usuario |
| A-03 | Si Gemini falla, `process_with_gemini` devuelve el texto del error ("…Usando datos locales.") pero **no** genera respuesta local. La función que sí la genera (`_local_chat_response`) solo es llamada desde `_call_gemini`, que no se usa | Respuesta de `/chat/message` sin API key | No cumple "debe usar respuesta local"; además expone el mensaje técnico del proveedor | Issue #4 (parte 2) |
| A-04 | `/execute` **no ejecuta** el script del tablero; el script subido con `PUT …/script` no tiene efecto, aunque su encabezado ofrece `query(sql)` | `/execute` devolvió lo mismo antes y después de subir otro script | Funcionalidad que aparenta existir y no existe | Issue #1 / #9 |
| A-05 | `/execute` ignora el tablero y sus widgets: todos los tableros muestran las mismas gráficas | Código de `execute_dashboard_script` | Los widgets son decorativos | Diseño |
| A-06 | `match_score` no está normalizado (puede superar 1) y el chat lo muestra como porcentaje | "coincidencia: 160%" | Mensaje confuso para el usuario | Bug menor |
| A-07 | El chat permite seleccionar `.pdf`, pero el backend lo rechaza (dentro de un 200) | `chat-upload` con PDF | Expectativa falsa hasta que se cierre el Issue #2 | Issue #2 |
| A-08 | Endpoints que crean recursos responden 200 en lugar de 201 (`/schema/tables`) y borrar una fila inexistente responde `deleted: true` | Ejemplos 5.3 y 5.7 | Inconsistencia de la API | Bug menor |
| A-09 | La llamada a Gemini (`chat.send_message`) es **síncrona** dentro de un endpoint `async` | `agent_tools_service.py` | Mientras Gemini responde, el proceso no atiende otras peticiones | Rendimiento |

---

## 7. Cómo reproducir los ejemplos

1. Levantar el entorno local (ver `README.md`).
2. Registrar una organización de prueba con correo `@example.com` e iniciar sesión guardando cookies (`curl -c cookies.txt`).
3. Cargar los CSV de `test-data/ferreteria/` con `POST /api/v1/schema/smart-upload`.
4. Ejecutar cada solicitud de este documento con `curl -b cookies.txt`, o desde Swagger en `http://localhost:8000/docs` (Swagger usa la cookie del navegador después del login).
