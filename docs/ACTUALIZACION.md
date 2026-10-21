# Actualización a la nueva versión

Esta guía es para quien estaba probando la versión anterior y debe pasar a la nueva. Todo lo que dice aquí fue verificado contra el código; lo que no se pudo verificar está marcado.

## 1. Qué trae la nueva versión

| Capacidad | Qué cambió para el usuario |
|---|---|
| **Carga inteligente** | Una sola zona de carga que acepta varios archivos y varias hojas a la vez. El sistema propone el tipo de cada hoja (ventas, compras, productos, etc.) y el rol de cada columna, y lo explica en lenguaje simple ("Esto es lo que entendí"). Se puede corregir y **deshacer una carga**. Ya no mezcla hojas de distinto tipo. |
| **Hallazgos de negocio** | La pantalla de Inicio y el Resumen de la semana muestran hallazgos calculados de forma exacta sobre los datos (mercancía parada, productos por agotarse, margen bajo, concentración de clientes), con el cálculo a la vista. |
| **Tableros creados por IA** | Los tableros ya no se crean a mano: se piden al asistente en el chat o con "Sugerir tableros". Cada gráfica se calcula sobre **todas** las filas. |
| **Edición por el asistente** | El asistente puede modificar un tablero existente. Cada edición guarda una versión y se puede **deshacer**. |
| **Detalle al clic y filtros** | Los gráficos son clicables y abren un panel con los registros que componen ese dato. Los tableros tienen filtros de periodo y categorías que viven en la URL. Los títulos y ejes usan nombres legibles. |
| **Chat con herramientas** | El asistente consulta los datos con herramientas de solo lectura (`describe_table`, `query_table`, `create_chart`) en lugar de recibir una muestra de filas en el prompt. |
| **Rediseño del frontend** | Nuevo sistema de diseño, colores de la universidad, accesibilidad en móvil. |
| **Robustez** | Solo owner o admin pueden borrar tableros, límites de uso por usuario, y se corrigió el bucle de login con cookie vieja. |

## 2. Qué cambió para quien probaba la versión anterior

| Antes | Ahora |
|---|---|
| Botón "Nuevo tablero" con formulario | **No existe.** Se pide en el chat o con "Sugerir tableros". |
| "Descargar su código" (script `.py`) y los endpoints `GET/PUT /dashboards/{id}/script` | **Eliminados.** Responden 404. |
| Todos los tableros mostraban las mismas gráficas | Cada gráfica es una especificación propia calculada con el motor de consultas. |
| `POST /dashboards/{id}/execute` sin cuerpo, hasta 500 filas por tabla | Acepta `{filters}` opcional y calcula sobre todas las filas. |
| Cualquier usuario podía borrar un tablero | Solo owner o admin. El resto recibe 403. |
| Subir un archivo a la vez a `/schema/smart-upload` | Varios archivos en una zona, con el flujo `/intake/*` y revisión solo si hay dudas. |
| Al subir el primer archivo no pasaba nada con los tableros | Si la organización no tiene tableros, se crean **1 a 3 tableros solos** (`DASHBOARD_AUTO_SUGGEST`). |
| Textos y selectores de la UI de la versión anterior | Cambiaron. Los guiones de prueba manual basados en textos de pantalla y los selectores de `frontend/e2e/` hay que revisarlos. |

Endpoints nuevos: `POST /dashboards/suggest`, `POST /dashboards/{id}/widgets/{wid}/drill`, `GET /dashboards/{id}/filter-options`, `POST /dashboards/{id}/undo-edit`, `GET /dashboards/{id}/versions`, `GET /insights`, `GET /intake/ontology`, `POST /intake/analyze`, `POST /intake/commit`, `POST /intake/undo`, `PUT /schema/tables/{id}/roles`. La UI nueva tiene la ruta `/resumen`.

## 3. Cómo actualizar tu copia local

```bash
git checkout main
git pull
```

- **Dependencias:** no cambian. `backend/requirements.txt`, `frontend/package.json` y `pnpm-lock.yaml` son idénticos a la versión anterior, así que no hay que reinstalar nada. Si algo falla al arrancar, ejecuta de nuevo `pip install -r requirements.txt` y `pnpm install`.
- **Variables de entorno:** la única obligatoria sigue siendo `APP_SECRET_KEY` (mínimo 32 caracteres). Las variables nuevas (límites del chat, de la carga inteligente y de los tableros) tienen todas un valor por defecto; no necesitas definirlas.
- **Esquema de base de datos:** no hay migraciones ni cambios de tablas. Los metadatos nuevos (rol de columna, tipo de hoja, rango de fechas) se guardan dentro de un campo JSONB existente. Tus bases de datos locales siguen funcionando.
- **Locale de Postgres:** las búsquedas sin distinguir mayúsculas dependen del locale. Verifica en tu base:

  ```sql
  SELECT lower('ÑANDÚ') = 'ñandú';   -- debe dar true
  ```

  La configuración probada es Postgres 18 inicializado con `--locale-provider=builtin --builtin-locale=C.UTF-8` (ver el `docker run` del README y `.github/workflows/ci.yml`). Con la imagen `postgres:15-alpine` que usaba el README anterior **no está verificado**. Si tu base local es de la versión anterior y el `SELECT` da `false`, recrea el contenedor con el comando del README (ese contenedor perderá sus datos locales; vuelve a cargar tus archivos de prueba).
- **Datos cargados con la versión anterior:** siguen funcionando. Los tableros viejos se muestran en modo `legacy` (con filtros activos no muestran cifras por hoja). Para que el chat conozca el rango de fechas de las tablas viejas, corre desde `backend/`:

  ```bash
  ./venv/Scripts/python.exe scripts/backfill_date_ranges.py --org-id <uuid>            # ensayo, no escribe
  ./venv/Scripts/python.exe scripts/backfill_date_ranges.py --org-id <uuid> --apply    # escribe
  ```

  Este script lee `DATABASE_*` de `backend/.env`: **confirma a qué base apunta antes de usar `--apply`**. Hazlo sin cargas de archivos en curso.
- **Scripts que NO son para el equipo de pruebas:** los `*_smoke_real_gemini.py` gastan cuota real de Gemini y levantan su propio Postgres.

## 4. Si trabajas sobre una rama creada antes de esta versión

Tu rama parte de un `main` desactualizado. Antes de seguir:

```bash
git fetch origin
git checkout <tu-rama>
git merge origin/main     # o git rebase origin/main
```

Si tu rama contiene documentación (por ejemplo `docs/API.md`, `ARCHITECTURE.md`, `DATABASE.md`, `SECURITY.md`), **revisa cada afirmación contra el código nuevo antes de fusionar**. Varias describen comportamientos que ya no existen: los scripts por tablero, el límite de 500 filas, la muestra de filas en el prompt del chat, la carga sin LLM, el registro que crea las hojas de servicios.

## 5. Limitaciones conocidas

Para que no se reporten como errores nuevos:

- `DELETE /schema/tables/{id}/rows/{rid}` responde `{"deleted": true}` aunque la fila no exista.
- La vista previa de `GET /files/{id}` devuelve siempre `preview_rows` vacío.
- El texto de ayuda del chat menciona PDF, pero el backend solo acepta CSV, Excel y JSON.
- Cada archivo subido por el chat consume cuota de mensajes aunque no llame a Gemini.
- Un CSV en UTF-8 con un solo byte latin-1 suelto se decodifica entero como cp1252 y las tildes salen mal.
- Los límites de uso de Gemini de la carga inteligente son en memoria por instancia: son un freno, no un contador exacto.
- No hay recuperación de contraseña ni política de contraseñas.
- Las listas de tokens revocados y el límite de peticiones por IP son en memoria por instancia.
- `GET /dashboards/{id}/versions` existe, pero la interfaz no lo usa.
- Con Gemini real solo se hicieron validaciones puntuales; la mayoría de las pruebas automáticas usan la ruta determinista o una base emulada. Si el asistente se comporta de forma rara, repórtalo: es justo lo que hay que validar.

## 6. Cómo reportar un problema

Abre un issue en GitHub con:

1. **Qué hiciste** (pasos, en orden).
2. **Qué esperabas** y **qué pasó**.
3. **Captura de pantalla** y, si hay, el mensaje de error completo.
4. **Versión:** salida de `git rev-parse --short HEAD`.
5. **Archivo de prueba** usado (nombre, o adjúntalo si no tiene datos reales).

Antes de reportar, revisa la sección 5.
