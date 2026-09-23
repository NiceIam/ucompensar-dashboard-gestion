-- ============================================================
-- PI0320251 — Solución WEB para la gestión estratégica de datos con IA
-- Fundación Universitaria Ucompensar — Grupo GIIS / Semillero Data Core Tech
--
-- Migration: 00004_business_templates.sql
-- Schemas basados en tipo de negocio — cuando una PYME se registra y
-- selecciona su tipo de negocio, el sistema auto-crea las tablas de datos
-- predefinidas para ese sector.
--
-- Depende de: 00001_initial_schema.sql, 00002_rls_policies.sql
-- ============================================================

-- ============================================================
-- TABLA: business_types
-- Catálogo global de tipos de negocio con sus esquemas predefinidos.
-- Sin org_id: es una tabla de referencia compartida (no tiene tenant).
-- Sin RLS de tenant: acceso de solo lectura para todos los autenticados.
-- ============================================================
CREATE TABLE public.business_types (
  id                     UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  name                   TEXT        NOT NULL UNIQUE,
  display_name           TEXT        NOT NULL,
  description            TEXT,
  icon                   TEXT,
  schema_definition      JSONB       NOT NULL
                                     CHECK (jsonb_typeof(schema_definition) = 'object'),
  default_kpis           JSONB       CHECK (jsonb_typeof(default_kpis) = 'array'),
  default_dashboard_config JSONB     CHECK (jsonb_typeof(default_dashboard_config) = 'object'),
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_business_types_name ON public.business_types (name);

-- ============================================================
-- ALTERAR: organizations — agregar business_type_id
-- ON DELETE SET NULL: si se elimina un tipo de negocio, la org no se pierde.
-- ============================================================
ALTER TABLE public.organizations
  ADD COLUMN business_type_id UUID REFERENCES public.business_types(id) ON DELETE SET NULL;

CREATE INDEX idx_organizations_business_type ON public.organizations (business_type_id);

-- ============================================================
-- TABLA: org_data_tables
-- Registro de las tablas de datos que cada org tiene activas.
-- Se crean automáticamente al registrarse según el business_type.
-- El operador también puede agregar tablas adicionales.
-- ============================================================
CREATE TABLE public.org_data_tables (
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              UUID        NOT NULL REFERENCES public.organizations(id) ON DELETE CASCADE,
  table_name          TEXT        NOT NULL
                                  CHECK (table_name ~ '^[a-z][a-z0-9_]{0,62}$'),
  display_name        TEXT        NOT NULL,
  columns_definition  JSONB       NOT NULL
                                  CHECK (jsonb_typeof(columns_definition) = 'array'),
  row_count           INTEGER     NOT NULL DEFAULT 0 CHECK (row_count >= 0),
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

  UNIQUE (org_id, table_name)
);

CREATE INDEX idx_org_data_tables_org_id ON public.org_data_tables (org_id);

CREATE TRIGGER tr_org_data_tables_updated_at
  BEFORE UPDATE ON public.org_data_tables
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- TABLA: org_data_rows
-- Filas de datos reales para cada tabla personalizada de una org.
-- RESTRICT en organizations: no se puede borrar una org con datos.
-- CASCADE en org_data_tables: al borrar la tabla, se borran sus filas.
-- ============================================================
CREATE TABLE public.org_data_rows (
  id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id     UUID        NOT NULL REFERENCES public.organizations(id) ON DELETE RESTRICT,
  table_id   UUID        NOT NULL REFERENCES public.org_data_tables(id) ON DELETE CASCADE,
  data       JSONB       NOT NULL CHECK (jsonb_typeof(data) = 'object'),
  source     TEXT        NOT NULL DEFAULT 'manual'
                         CHECK (source IN ('manual', 'chatbot', 'etl', 'pdf')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Índice principal: satisface RLS (org_id) + filtro de tabla en un solo scan
CREATE INDEX idx_org_data_rows_org_table ON public.org_data_rows (org_id, table_id);
-- Índice GIN: búsqueda por campos dentro del JSONB de datos
CREATE INDEX idx_org_data_rows_data_gin  ON public.org_data_rows USING GIN (data);

CREATE TRIGGER tr_org_data_rows_updated_at
  BEFORE UPDATE ON public.org_data_rows
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- TABLA: etl_jobs
-- Seguimiento de trabajos de ingesta de datos (CSV, Excel, PDF, etc.).
-- Cada job pertenece a una org y puede cargar datos en una o varias tablas.
-- RESTRICT en organizations: los jobs son evidencia de actividad — no se borran.
-- ============================================================
CREATE TABLE public.etl_jobs (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id           UUID        NOT NULL REFERENCES public.organizations(id) ON DELETE RESTRICT,
  source_type      TEXT        NOT NULL
                               CHECK (source_type IN ('pdf', 'csv', 'excel', 'database', 'chatbot', 'api')),
  source_metadata  JSONB       CHECK (jsonb_typeof(source_metadata) = 'object'),
  status           TEXT        NOT NULL DEFAULT 'pending'
                               CHECK (status IN ('pending', 'extracting', 'transforming', 'loading', 'completed', 'failed')),
  rows_extracted   INTEGER     NOT NULL DEFAULT 0 CHECK (rows_extracted >= 0),
  rows_loaded      INTEGER     NOT NULL DEFAULT 0 CHECK (rows_loaded >= 0),
  error_message    TEXT,
  started_at       TIMESTAMPTZ,
  completed_at     TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_etl_jobs_org_id     ON public.etl_jobs (org_id);
-- Índice compuesto: consulta más común — jobs activos o fallidos de una org
CREATE INDEX idx_etl_jobs_org_status ON public.etl_jobs (org_id, status);
-- Índice parcial: solo jobs en vuelo — los completados/fallidos son histórico
CREATE INDEX idx_etl_jobs_in_flight
  ON public.etl_jobs (org_id, created_at)
  WHERE status IN ('pending', 'extracting', 'transforming', 'loading');

-- ============================================================
-- HABILITAR RLS EN NUEVAS TABLAS
-- business_types: RLS habilitado pero con política de solo lectura pública
--   (todos los autenticados ven todos los tipos — es un catálogo global)
-- Las demás tablas siguen el patrón estándar de tenant isolation.
-- ============================================================
ALTER TABLE public.business_types   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.org_data_tables  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.org_data_rows    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.etl_jobs         ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- POLÍTICAS: business_types
--
-- SELECT: cualquier usuario autenticado puede leer el catálogo global
-- INSERT/UPDATE/DELETE: solo el service_role (backend) puede modificar
--   el catálogo — no se expone a usuarios del cliente
-- ============================================================
CREATE POLICY "business_types_public_read"
  ON public.business_types
  FOR SELECT
  TO authenticated
  USING (true);

-- ============================================================
-- POLÍTICAS: org_data_tables
--
-- SELECT: cualquier miembro puede ver las tablas de su org
-- INSERT: el backend crea tablas al registrar la org o cuando el usuario agrega una
-- UPDATE: owner/admin pueden modificar definición de columnas
-- DELETE: owner/admin pueden eliminar tablas (elimina también sus filas en cascada)
-- ============================================================
CREATE POLICY "org_data_tables_org_select"
  ON public.org_data_tables
  FOR SELECT
  USING (org_id = get_user_org_id());

CREATE POLICY "org_data_tables_org_insert"
  ON public.org_data_tables
  FOR INSERT
  WITH CHECK (org_id = get_user_org_id());

CREATE POLICY "org_data_tables_admin_update"
  ON public.org_data_tables
  FOR UPDATE
  USING (
    org_id = get_user_org_id()
    AND get_user_role() IN ('owner', 'admin')
  )
  WITH CHECK (
    org_id = get_user_org_id()
    AND get_user_role() IN ('owner', 'admin')
  );

CREATE POLICY "org_data_tables_admin_delete"
  ON public.org_data_tables
  FOR DELETE
  USING (
    org_id = get_user_org_id()
    AND get_user_role() IN ('owner', 'admin')
  );

-- ============================================================
-- POLÍTICAS: org_data_rows
--
-- SELECT: cualquier miembro puede leer los datos de su org
-- INSERT: cualquier miembro puede agregar filas (carga manual o ETL)
-- UPDATE: cualquier miembro puede corregir filas (edición en plataforma)
-- DELETE: owner/admin pueden eliminar filas individuales
-- ============================================================
CREATE POLICY "org_data_rows_org_select"
  ON public.org_data_rows
  FOR SELECT
  USING (org_id = get_user_org_id());

CREATE POLICY "org_data_rows_org_insert"
  ON public.org_data_rows
  FOR INSERT
  WITH CHECK (org_id = get_user_org_id());

CREATE POLICY "org_data_rows_org_update"
  ON public.org_data_rows
  FOR UPDATE
  USING (org_id = get_user_org_id())
  WITH CHECK (org_id = get_user_org_id());

CREATE POLICY "org_data_rows_admin_delete"
  ON public.org_data_rows
  FOR DELETE
  USING (
    org_id = get_user_org_id()
    AND get_user_role() IN ('owner', 'admin')
  );

-- ============================================================
-- POLÍTICAS: etl_jobs
--
-- SELECT: cualquier miembro puede ver el historial de jobs de su org
-- INSERT: el backend crea jobs al iniciar una ingesta
-- UPDATE: el backend actualiza el status durante la ejecución
-- No hay política DELETE: los jobs son histórico inmutable
-- ============================================================
CREATE POLICY "etl_jobs_org_select"
  ON public.etl_jobs
  FOR SELECT
  USING (org_id = get_user_org_id());

CREATE POLICY "etl_jobs_org_insert"
  ON public.etl_jobs
  FOR INSERT
  WITH CHECK (org_id = get_user_org_id());

CREATE POLICY "etl_jobs_org_update"
  ON public.etl_jobs
  FOR UPDATE
  USING (org_id = get_user_org_id())
  WITH CHECK (org_id = get_user_org_id());

-- ============================================================
-- GRANTS: Permisos para roles de Supabase
-- ============================================================

-- business_types: solo lectura para usuarios autenticados
GRANT SELECT ON public.business_types TO authenticated;

-- org_data_tables: gestión completa (DELETE real permitido vía política admin)
GRANT SELECT, INSERT, UPDATE, DELETE ON public.org_data_tables TO authenticated;

-- org_data_rows: gestión completa (DELETE real permitido vía política admin)
GRANT SELECT, INSERT, UPDATE, DELETE ON public.org_data_rows TO authenticated;

-- etl_jobs: lectura + escritura de estado (INSERT/UPDATE del backend)
GRANT SELECT, INSERT, UPDATE ON public.etl_jobs TO authenticated;

-- ============================================================
-- FUNCIÓN: Inicializar tablas de datos al registrar una org
-- Llamada por el backend (FastAPI) con service_role después de crear la org
-- y asignar el business_type_id. Inserta una fila en org_data_tables
-- por cada tabla definida en el schema_definition del business_type.
-- ============================================================
CREATE OR REPLACE FUNCTION initialize_org_data_tables(p_org_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_schema       JSONB;
  v_table        JSONB;
  v_count        INTEGER := 0;
BEGIN
  -- Obtener el schema_definition del tipo de negocio asignado a la org
  SELECT bt.schema_definition
    INTO v_schema
    FROM public.organizations o
    JOIN public.business_types bt ON bt.id = o.business_type_id
   WHERE o.id = p_org_id;

  IF v_schema IS NULL THEN
    RAISE EXCEPTION 'La organización % no tiene business_type_id asignado', p_org_id;
  END IF;

  -- Iterar sobre cada tabla del schema e insertarla en org_data_tables
  FOR v_table IN SELECT * FROM jsonb_array_elements(v_schema -> 'tables')
  LOOP
    INSERT INTO public.org_data_tables (org_id, table_name, display_name, columns_definition)
    VALUES (
      p_org_id,
      v_table ->> 'name',
      v_table ->> 'display_name',
      v_table -> 'columns'
    )
    ON CONFLICT (org_id, table_name) DO NOTHING;

    v_count := v_count + 1;
  END LOOP;

  RETURN v_count;
END;
$$;

GRANT EXECUTE ON FUNCTION initialize_org_data_tables(UUID) TO authenticated;

-- ============================================================
-- FUNCIÓN: Contar filas en org_data_rows de una tabla específica
-- Complementa count_org_records() que cuenta data_records del sistema anterior.
-- Usado por el backend para actualizar org_data_tables.row_count.
-- ============================================================
CREATE OR REPLACE FUNCTION count_table_rows(p_org_id UUID, p_table_id UUID)
RETURNS INTEGER
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT COUNT(*)::INTEGER
  FROM public.org_data_rows
  WHERE org_id = p_org_id
    AND table_id = p_table_id;
$$;

GRANT EXECUTE ON FUNCTION count_table_rows(UUID, UUID) TO authenticated;

-- ============================================================
-- DATOS: Tipos de negocio predefinidos
-- 3 plantillas para el prototipo PI0320251
-- Sectores objetivo: comercio (ferretería), servicios, restaurante
-- ============================================================

-- ------------------------------------------------------------
-- Template 1: Ferretería / Comercio
-- ------------------------------------------------------------
INSERT INTO public.business_types (
  name,
  display_name,
  description,
  icon,
  schema_definition,
  default_kpis,
  default_dashboard_config
) VALUES (
  'ferreteria',
  'Ferretería / Comercio',
  'Negocios de venta de productos físicos: ferretería, papelería, miscelánea, comercio al por menor.',
  'store',
  '{
    "tables": [
      {
        "name": "productos",
        "display_name": "Productos",
        "columns": [
          {"name": "nombre",        "type": "text",     "label": "Nombre del producto",  "required": true},
          {"name": "categoria",     "type": "text",     "label": "Categoría",            "required": false},
          {"name": "precio_compra", "type": "currency", "label": "Precio de compra",     "required": false},
          {"name": "precio_venta",  "type": "currency", "label": "Precio de venta",      "required": true},
          {"name": "stock_actual",  "type": "integer",  "label": "Stock actual",         "required": false},
          {"name": "stock_minimo",  "type": "integer",  "label": "Stock mínimo",         "required": false},
          {"name": "proveedor",     "type": "text",     "label": "Proveedor",            "required": false},
          {"name": "codigo_barras", "type": "text",     "label": "Código de barras",     "required": false}
        ]
      },
      {
        "name": "ventas",
        "display_name": "Ventas",
        "columns": [
          {"name": "fecha",           "type": "date",     "label": "Fecha",           "required": true},
          {"name": "producto",        "type": "text",     "label": "Producto",        "required": true},
          {"name": "cantidad",        "type": "integer",  "label": "Cantidad",        "required": true},
          {"name": "precio_unitario", "type": "currency", "label": "Precio unitario", "required": false},
          {"name": "total",           "type": "currency", "label": "Total",           "required": true},
          {"name": "metodo_pago",     "type": "text",     "label": "Método de pago",  "required": false},
          {"name": "cliente",         "type": "text",     "label": "Cliente",         "required": false}
        ]
      },
      {
        "name": "proveedores",
        "display_name": "Proveedores",
        "columns": [
          {"name": "nombre",    "type": "text", "label": "Nombre",                   "required": true},
          {"name": "contacto",  "type": "text", "label": "Contacto",                 "required": false},
          {"name": "telefono",  "type": "text", "label": "Teléfono",                 "required": false},
          {"name": "email",     "type": "text", "label": "Email",                    "required": false},
          {"name": "productos", "type": "text", "label": "Productos que suministra", "required": false}
        ]
      }
    ]
  }'::jsonb,
  '[
    {"id": "total_ventas",            "label": "Total ventas del mes",       "table": "ventas",    "column": "total",        "aggregation": "sum",   "filter": "current_month"},
    {"id": "margen_promedio",         "label": "Margen promedio (%)",        "table": "productos", "column": null,           "aggregation": "margin","formula": "(precio_venta - precio_compra) / precio_venta * 100"},
    {"id": "productos_bajo_stock",    "label": "Productos bajo stock mínimo","table": "productos", "column": "stock_actual", "aggregation": "count", "condition": "stock_actual < stock_minimo"},
    {"id": "top5_productos",          "label": "Top 5 productos vendidos",   "table": "ventas",    "column": "producto",     "aggregation": "top5",  "order_by": "cantidad"}
  ]'::jsonb,
  '{
    "layout": "grid",
    "widgets": [
      {"type": "kpi",   "title": "Total ventas del mes",        "kpi_id": "total_ventas",         "position": {"x": 0, "y": 0, "w": 3, "h": 2}},
      {"type": "kpi",   "title": "Margen promedio",             "kpi_id": "margen_promedio",       "position": {"x": 3, "y": 0, "w": 3, "h": 2}},
      {"type": "kpi",   "title": "Productos bajo stock",        "kpi_id": "productos_bajo_stock",  "position": {"x": 6, "y": 0, "w": 3, "h": 2}},
      {"type": "bar",   "title": "Ventas por producto",         "table": "ventas",   "x": "producto",  "y": "total",    "position": {"x": 0, "y": 2, "w": 6, "h": 4}},
      {"type": "line",  "title": "Tendencia de ventas",         "table": "ventas",   "x": "fecha",     "y": "total",    "position": {"x": 6, "y": 2, "w": 6, "h": 4}},
      {"type": "pie",   "title": "Ventas por método de pago",   "table": "ventas",   "x": "metodo_pago","y": "total",   "position": {"x": 0, "y": 6, "w": 4, "h": 4}},
      {"type": "table", "title": "Stock de productos",          "table": "productos","columns": ["nombre","categoria","stock_actual","stock_minimo","precio_venta"], "position": {"x": 4, "y": 6, "w": 8, "h": 4}}
    ]
  }'::jsonb
);

-- ------------------------------------------------------------
-- Template 2: Empresa de Servicios
-- ------------------------------------------------------------
INSERT INTO public.business_types (
  name,
  display_name,
  description,
  icon,
  schema_definition,
  default_kpis,
  default_dashboard_config
) VALUES (
  'servicios',
  'Empresa de Servicios',
  'Empresas que venden servicios: consultoría, mantenimiento, diseño, asesoría, TIC, salud, educación.',
  'briefcase',
  '{
    "tables": [
      {
        "name": "servicios",
        "display_name": "Servicios",
        "columns": [
          {"name": "nombre",          "type": "text",     "label": "Nombre del servicio", "required": true},
          {"name": "descripcion",     "type": "text",     "label": "Descripción",         "required": false},
          {"name": "precio",          "type": "currency", "label": "Precio",              "required": true},
          {"name": "duracion_horas",  "type": "number",   "label": "Duración (horas)",    "required": false},
          {"name": "categoria",       "type": "text",     "label": "Categoría",           "required": false}
        ]
      },
      {
        "name": "clientes",
        "display_name": "Clientes",
        "columns": [
          {"name": "nombre",   "type": "text", "label": "Nombre",  "required": true},
          {"name": "email",    "type": "text", "label": "Email",   "required": false},
          {"name": "telefono", "type": "text", "label": "Teléfono","required": false},
          {"name": "empresa",  "type": "text", "label": "Empresa", "required": false},
          {"name": "notas",    "type": "text", "label": "Notas",   "required": false}
        ]
      },
      {
        "name": "facturacion",
        "display_name": "Facturación",
        "columns": [
          {"name": "fecha",        "type": "date",     "label": "Fecha",             "required": true},
          {"name": "cliente",      "type": "text",     "label": "Cliente",           "required": true},
          {"name": "servicio",     "type": "text",     "label": "Servicio",          "required": false},
          {"name": "monto",        "type": "currency", "label": "Monto",             "required": true},
          {"name": "estado",       "type": "text",     "label": "Estado de pago",    "required": false},
          {"name": "metodo_pago",  "type": "text",     "label": "Método de pago",    "required": false}
        ]
      }
    ]
  }'::jsonb,
  '[
    {"id": "ingresos_mes",          "label": "Ingresos del mes",        "table": "facturacion", "column": "monto",   "aggregation": "sum",   "filter": "current_month"},
    {"id": "clientes_activos",      "label": "Clientes activos",        "table": "clientes",    "column": "nombre",  "aggregation": "count"},
    {"id": "facturas_pendientes",   "label": "Facturas pendientes",     "table": "facturacion", "column": "monto",   "aggregation": "sum",   "condition": "estado = ''pendiente''"},
    {"id": "servicio_mas_vendido",  "label": "Servicio más vendido",    "table": "facturacion", "column": "servicio","aggregation": "top1",  "order_by": "count"}
  ]'::jsonb,
  '{
    "layout": "grid",
    "widgets": [
      {"type": "kpi",   "title": "Ingresos del mes",          "kpi_id": "ingresos_mes",         "position": {"x": 0, "y": 0, "w": 3, "h": 2}},
      {"type": "kpi",   "title": "Clientes activos",          "kpi_id": "clientes_activos",      "position": {"x": 3, "y": 0, "w": 3, "h": 2}},
      {"type": "kpi",   "title": "Facturas pendientes",       "kpi_id": "facturas_pendientes",   "position": {"x": 6, "y": 0, "w": 3, "h": 2}},
      {"type": "bar",   "title": "Ingresos por servicio",     "table": "facturacion", "x": "servicio",    "y": "monto", "position": {"x": 0, "y": 2, "w": 6, "h": 4}},
      {"type": "line",  "title": "Ingresos mensuales",        "table": "facturacion", "x": "fecha",       "y": "monto", "position": {"x": 6, "y": 2, "w": 6, "h": 4}},
      {"type": "pie",   "title": "Estado de facturas",        "table": "facturacion", "x": "estado",      "y": "monto", "position": {"x": 0, "y": 6, "w": 4, "h": 4}},
      {"type": "table", "title": "Últimas facturas",          "table": "facturacion", "columns": ["fecha","cliente","servicio","monto","estado"], "position": {"x": 4, "y": 6, "w": 8, "h": 4}}
    ]
  }'::jsonb
);

-- ------------------------------------------------------------
-- Template 3: Restaurante / Alimentos
-- ------------------------------------------------------------
INSERT INTO public.business_types (
  name,
  display_name,
  description,
  icon,
  schema_definition,
  default_kpis,
  default_dashboard_config
) VALUES (
  'restaurante',
  'Restaurante / Alimentos',
  'Establecimientos de comida y bebida: restaurantes, cafeterías, panaderías, servicios de catering.',
  'utensils',
  '{
    "tables": [
      {
        "name": "menu",
        "display_name": "Menú",
        "columns": [
          {"name": "plato",              "type": "text",     "label": "Nombre del plato",    "required": true},
          {"name": "categoria",          "type": "text",     "label": "Categoría",           "required": false},
          {"name": "precio",             "type": "currency", "label": "Precio",              "required": true},
          {"name": "costo_preparacion",  "type": "currency", "label": "Costo de preparación","required": false},
          {"name": "disponible",         "type": "boolean",  "label": "Disponible",          "required": false}
        ]
      },
      {
        "name": "pedidos",
        "display_name": "Pedidos",
        "columns": [
          {"name": "fecha",       "type": "date",     "label": "Fecha",              "required": true},
          {"name": "mesa",        "type": "text",     "label": "Mesa / Domicilio",   "required": false},
          {"name": "platos",      "type": "text",     "label": "Platos pedidos",     "required": false},
          {"name": "total",       "type": "currency", "label": "Total",              "required": true},
          {"name": "metodo_pago", "type": "text",     "label": "Método de pago",     "required": false},
          {"name": "propina",     "type": "currency", "label": "Propina",            "required": false}
        ]
      },
      {
        "name": "inventario",
        "display_name": "Inventario / Insumos",
        "columns": [
          {"name": "insumo",             "type": "text",   "label": "Insumo",                "required": true},
          {"name": "cantidad",           "type": "number", "label": "Cantidad",              "required": false},
          {"name": "unidad",             "type": "text",   "label": "Unidad de medida",      "required": false},
          {"name": "precio_unitario",    "type": "currency","label": "Precio unitario",      "required": false},
          {"name": "proveedor",          "type": "text",   "label": "Proveedor",             "required": false},
          {"name": "fecha_vencimiento",  "type": "date",   "label": "Fecha de vencimiento",  "required": false}
        ]
      }
    ]
  }'::jsonb,
  '[
    {"id": "ventas_dia",           "label": "Ventas del día",      "table": "pedidos", "column": "total",   "aggregation": "sum",    "filter": "today"},
    {"id": "ticket_promedio",      "label": "Ticket promedio",     "table": "pedidos", "column": "total",   "aggregation": "avg"},
    {"id": "plato_mas_vendido",    "label": "Plato más vendido",   "table": "pedidos", "column": "platos",  "aggregation": "top1",   "order_by": "count"},
    {"id": "costo_vs_ingreso",     "label": "Costo vs Ingreso (%)", "table": "menu",   "column": null,      "aggregation": "ratio",  "formula": "costo_preparacion / precio * 100"}
  ]'::jsonb,
  '{
    "layout": "grid",
    "widgets": [
      {"type": "kpi",   "title": "Ventas del día",              "kpi_id": "ventas_dia",        "position": {"x": 0, "y": 0, "w": 3, "h": 2}},
      {"type": "kpi",   "title": "Ticket promedio",             "kpi_id": "ticket_promedio",   "position": {"x": 3, "y": 0, "w": 3, "h": 2}},
      {"type": "kpi",   "title": "Plato más vendido",           "kpi_id": "plato_mas_vendido", "position": {"x": 6, "y": 0, "w": 3, "h": 2}},
      {"type": "bar",   "title": "Pedidos por mesa",            "table": "pedidos",  "x": "mesa",        "y": "total",  "position": {"x": 0, "y": 2, "w": 6, "h": 4}},
      {"type": "line",  "title": "Ventas por día",              "table": "pedidos",  "x": "fecha",       "y": "total",  "position": {"x": 6, "y": 2, "w": 6, "h": 4}},
      {"type": "pie",   "title": "Ventas por método de pago",   "table": "pedidos",  "x": "metodo_pago", "y": "total",  "position": {"x": 0, "y": 6, "w": 4, "h": 4}},
      {"type": "table", "title": "Menú activo",                 "table": "menu",     "columns": ["plato","categoria","precio","costo_preparacion","disponible"], "position": {"x": 4, "y": 6, "w": 8, "h": 4}}
    ]
  }'::jsonb
);
