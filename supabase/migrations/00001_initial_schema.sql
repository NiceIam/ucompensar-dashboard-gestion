-- ============================================================
-- PI0320251 — Solución WEB para la gestión estratégica de datos con IA
-- Fundación Universitaria Ucompensar — Grupo GIIS / Semillero Data Core Tech
--
-- Migration: 00001_initial_schema.sql
-- Motor: Supabase (PostgreSQL 15)
-- Multi-tenancy: Row Level Security (RLS) por org_id
-- ============================================================

-- ============================================================
-- EXTENSIONS
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pg_trgm";    -- búsqueda fuzzy de texto

-- ============================================================
-- TRIGGER FUNCTION: auto-actualizar updated_at
-- Compartida por todas las tablas que tienen columna updated_at
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

-- ============================================================
-- TABLA: organizations
-- Cada PYME/MIPYME es una organización. Unidad base de multi-tenancy.
-- Esta tabla NO tiene org_id — es la raíz del modelo multi-tenant.
-- ============================================================
CREATE TABLE public.organizations (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  name         TEXT        NOT NULL,
  sector       TEXT        CHECK (sector IN ('terciario', 'cuaternario', 'TIC', 'salud', 'educacion', 'comercio')),
  size         TEXT        CHECK (size IN ('micro', 'pequeña', 'mediana')),
  nit          TEXT        UNIQUE,
  city         TEXT        NOT NULL DEFAULT 'Bogotá',
  plan_type    TEXT        NOT NULL DEFAULT 'free'
                           CHECK (plan_type IN ('free', 'basic', 'pro')),
  max_records  INTEGER     NOT NULL DEFAULT 10000
                           CHECK (max_records > 0),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_organizations_plan ON public.organizations (plan_type);

CREATE TRIGGER tr_organizations_updated_at
  BEFORE UPDATE ON public.organizations
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- TABLA: profiles
-- Usuarios de la plataforma, ligados a Supabase Auth y a una organización.
-- PK = auth.users.id para integración nativa con Supabase Auth.
-- ============================================================
CREATE TABLE public.profiles (
  id           UUID        PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  org_id       UUID        NOT NULL REFERENCES public.organizations(id) ON DELETE RESTRICT,
  full_name    TEXT        NOT NULL,
  role         TEXT        NOT NULL DEFAULT 'viewer'
                           CHECK (role IN ('owner', 'admin', 'viewer')),
  email        TEXT        NOT NULL,
  avatar_url   TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_profiles_org_id ON public.profiles (org_id);
CREATE INDEX idx_profiles_email  ON public.profiles (email);

CREATE TRIGGER tr_profiles_updated_at
  BEFORE UPDATE ON public.profiles
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- TABLA: uploaded_files
-- Archivos CSV/Excel/JSON subidos por los usuarios.
-- Soft delete con deleted_at — nunca DELETE FROM.
-- ============================================================
CREATE TABLE public.uploaded_files (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id           UUID        NOT NULL REFERENCES public.organizations(id) ON DELETE RESTRICT,
  user_id          UUID        NOT NULL REFERENCES public.profiles(id) ON DELETE RESTRICT,
  filename         TEXT        NOT NULL,
  file_path        TEXT        NOT NULL,
  file_type        TEXT        NOT NULL
                               CHECK (file_type IN ('csv', 'xlsx', 'json')),
  file_size_bytes  INTEGER     CHECK (file_size_bytes > 0),
  rows_count       INTEGER     CHECK (rows_count >= 0),
  columns_detected JSONB       CHECK (jsonb_typeof(columns_detected) = 'array'),
  status           TEXT        NOT NULL DEFAULT 'pending'
                               CHECK (status IN ('pending', 'processing', 'ready', 'error')),
  error_message    TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  processed_at     TIMESTAMPTZ,
  deleted_at       TIMESTAMPTZ
);

CREATE INDEX idx_uploaded_files_org_id ON public.uploaded_files (org_id);
-- Índice compuesto: filtro más común — archivos de una org por estado
CREATE INDEX idx_uploaded_files_org_status ON public.uploaded_files (org_id, status);
-- Índice parcial: solo archivos activos — muy eficiente para queries del día a día
CREATE INDEX idx_uploaded_files_active
  ON public.uploaded_files (org_id)
  WHERE deleted_at IS NULL;

CREATE TRIGGER tr_uploaded_files_updated_at
  BEFORE UPDATE ON public.uploaded_files
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- TABLA: data_records
-- Registros individuales de datos normalizados a JSONB.
-- Diseñada para < 10.000 registros/org en fase prototipo.
-- ============================================================
CREATE TABLE public.data_records (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  file_id     UUID        NOT NULL REFERENCES public.uploaded_files(id) ON DELETE CASCADE,
  org_id      UUID        NOT NULL REFERENCES public.organizations(id) ON DELETE RESTRICT,
  row_number  INTEGER     NOT NULL CHECK (row_number >= 0),
  data        JSONB       NOT NULL CHECK (jsonb_typeof(data) = 'object'),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Índice compuesto principal: satisface RLS (org_id) y el filtro por archivo en un solo scan
CREATE INDEX idx_data_records_org_file  ON public.data_records (org_id, file_id);
-- Índice para COUNT y paginación por archivo
CREATE INDEX idx_data_records_file_id   ON public.data_records (file_id);
-- Índice GIN para búsqueda dentro de los campos JSONB
CREATE INDEX idx_data_records_data_gin  ON public.data_records USING GIN (data);

-- ============================================================
-- TABLA: agent_sessions
-- Registro de cada ejecución del pipeline de agentes IA (Google ADK).
-- ============================================================
CREATE TABLE public.agent_sessions (
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              UUID        NOT NULL REFERENCES public.organizations(id) ON DELETE RESTRICT,
  user_id             UUID        NOT NULL REFERENCES public.profiles(id) ON DELETE RESTRICT,
  file_id             UUID        NOT NULL REFERENCES public.uploaded_files(id) ON DELETE RESTRICT,
  status              TEXT        NOT NULL DEFAULT 'pending'
                                  CHECK (status IN ('pending', 'running', 'completed', 'failed')),
  started_at          TIMESTAMPTZ,
  completed_at        TIMESTAMPTZ,
  error_message       TEXT,
  gemini_tokens_used  INTEGER     CHECK (gemini_tokens_used >= 0),
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_agent_sessions_org_id     ON public.agent_sessions (org_id);
CREATE INDEX idx_agent_sessions_file_id    ON public.agent_sessions (file_id);
-- Índice compuesto para filtrar sesiones activas de una org
CREATE INDEX idx_agent_sessions_org_status ON public.agent_sessions (org_id, status);

-- ============================================================
-- TABLA: agent_results
-- Resultados de cada agente en el pipeline ADK.
-- UNIQUE en (session_id, agent_name): un resultado por agente por sesión.
-- ============================================================
CREATE TABLE public.agent_results (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id        UUID        NOT NULL REFERENCES public.agent_sessions(id) ON DELETE CASCADE,
  org_id            UUID        NOT NULL REFERENCES public.organizations(id) ON DELETE RESTRICT,
  agent_name        TEXT        NOT NULL
                                CHECK (agent_name IN ('data_cleaner', 'data_analyzer', 'insight_generator', 'dashboard_config')),
  output            JSONB       NOT NULL CHECK (jsonb_typeof(output) = 'object'),
  execution_time_ms INTEGER     CHECK (execution_time_ms >= 0),
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- Idempotencia del pipeline: no se puede duplicar un resultado por agente
  UNIQUE (session_id, agent_name)
);

CREATE INDEX idx_agent_results_org_id     ON public.agent_results (org_id);
CREATE INDEX idx_agent_results_session_id ON public.agent_results (session_id);

-- ============================================================
-- TABLA: dashboards
-- Tableros de control de cada organización.
-- Soft delete con deleted_at — nunca DELETE FROM.
-- ============================================================
CREATE TABLE public.dashboards (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      UUID        NOT NULL REFERENCES public.organizations(id) ON DELETE RESTRICT,
  user_id     UUID        NOT NULL REFERENCES public.profiles(id) ON DELETE RESTRICT,
  name        TEXT        NOT NULL,
  description TEXT,
  -- ON DELETE SET NULL: el dashboard sobrevive a la eliminación del archivo
  file_id     UUID        REFERENCES public.uploaded_files(id) ON DELETE SET NULL,
  -- ON DELETE SET NULL: el dashboard sobrevive a la eliminación de la sesión de IA
  session_id  UUID        REFERENCES public.agent_sessions(id) ON DELETE SET NULL,
  is_default  BOOLEAN     NOT NULL DEFAULT false,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at  TIMESTAMPTZ
);

CREATE INDEX idx_dashboards_org_id ON public.dashboards (org_id);
-- Índice parcial: solo dashboards activos — query más común
CREATE INDEX idx_dashboards_active
  ON public.dashboards (org_id)
  WHERE deleted_at IS NULL;

CREATE TRIGGER tr_dashboards_updated_at
  BEFORE UPDATE ON public.dashboards
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- TABLA: widgets
-- Widgets (gráficas/KPIs) dentro de un dashboard.
-- ON DELETE CASCADE respecto a dashboards.
-- ============================================================
CREATE TABLE public.widgets (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  dashboard_id UUID        NOT NULL REFERENCES public.dashboards(id) ON DELETE CASCADE,
  org_id       UUID        NOT NULL REFERENCES public.organizations(id) ON DELETE RESTRICT,
  chart_type   TEXT        NOT NULL
                           CHECK (chart_type IN ('bar', 'line', 'area', 'pie', 'kpi', 'table')),
  title        TEXT        NOT NULL,
  config       JSONB       NOT NULL CHECK (jsonb_typeof(config) = 'object'),
  position_x   INTEGER     NOT NULL DEFAULT 0 CHECK (position_x >= 0),
  position_y   INTEGER     NOT NULL DEFAULT 0 CHECK (position_y >= 0),
  width        INTEGER     NOT NULL DEFAULT 6 CHECK (width BETWEEN 1 AND 12),
  height       INTEGER     NOT NULL DEFAULT 4 CHECK (height > 0),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_widgets_dashboard_id ON public.widgets (dashboard_id);
CREATE INDEX idx_widgets_org_id       ON public.widgets (org_id);

CREATE TRIGGER tr_widgets_updated_at
  BEFORE UPDATE ON public.widgets
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- TABLA: chat_messages
-- Historial de conversaciones con el chatbot.
-- session_id es generado en frontend (UUID sin FK) — flexibilidad de cliente.
-- ============================================================
CREATE TABLE public.chat_messages (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id       UUID        NOT NULL REFERENCES public.organizations(id) ON DELETE RESTRICT,
  user_id      UUID        NOT NULL REFERENCES public.profiles(id) ON DELETE RESTRICT,
  session_id   UUID        NOT NULL,  -- ID de sesión de chat; generado en frontend, sin FK
  role         TEXT        NOT NULL
                           CHECK (role IN ('user', 'assistant')),
  content      TEXT        NOT NULL,
  context_used JSONB,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_chat_messages_org_id  ON public.chat_messages (org_id);
-- Índice compuesto para cargar el historial de una sesión de chat
CREATE INDEX idx_chat_messages_session ON public.chat_messages (org_id, session_id);
-- Índice compuesto para filtrar mensajes de un usuario
CREATE INDEX idx_chat_messages_user    ON public.chat_messages (org_id, user_id);

-- ============================================================
-- TABLA: audit_log
-- Log inmutable de acciones importantes (compliance académico).
-- org_id y user_id usan ON DELETE SET NULL — los logs nunca se pierden.
-- Esta es la ÚNICA tabla donde org_id puede ser NULL.
-- ============================================================
CREATE TABLE public.audit_log (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  -- ON DELETE SET NULL: el registro sobrevive a la eliminación de la org
  org_id        UUID        REFERENCES public.organizations(id) ON DELETE SET NULL,
  -- ON DELETE SET NULL: el registro sobrevive a la eliminación del usuario
  user_id       UUID        REFERENCES public.profiles(id) ON DELETE SET NULL,
  action        TEXT        NOT NULL
                            CHECK (action IN (
                              'file_uploaded', 'file_deleted',
                              'agent_run', 'agent_failed',
                              'dashboard_created', 'dashboard_deleted',
                              'user_invited', 'login', 'logout'
                            )),
  resource_type TEXT        CHECK (resource_type IN ('file', 'dashboard', 'agent_session', 'profile')),
  resource_id   UUID,
  details       JSONB,
  ip_address    INET,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_log_org_id     ON public.audit_log (org_id);
-- Índice compuesto para filtrar por tipo de acción de una org
CREATE INDEX idx_audit_log_org_action ON public.audit_log (org_id, action);
-- Índice para consultas de auditoría por rango de fechas
CREATE INDEX idx_audit_log_created_at ON public.audit_log (created_at);

-- ============================================================
-- TRIGGER: Crear perfil automáticamente al registrar usuario
-- Se activa en auth.users para mantener sincronía con profiles.
-- org_id viene de raw_user_meta_data (se pasa en el signup desde el frontend).
-- ============================================================
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.profiles (id, email, full_name, org_id, role)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.email),
    (NEW.raw_user_meta_data->>'org_id')::UUID,
    'owner'
  );
  RETURN NEW;
END;
$$;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- ============================================================
-- FUNCIÓN: Contar registros activos de una organización
-- Usada para validar el límite de 10.000 registros del prototipo.
-- El backend (FastAPI) debe llamar esta función antes de procesar un archivo.
-- ============================================================
CREATE OR REPLACE FUNCTION count_org_records(p_org_id UUID)
RETURNS INTEGER
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT COUNT(*)::INTEGER
  FROM public.data_records
  WHERE org_id = p_org_id;
$$;

-- ============================================================
-- FUNCIÓN: Verificar si la org puede subir más registros
-- Retorna TRUE si hay capacidad disponible.
-- Uso desde FastAPI: SELECT org_can_upload('uuid-de-la-org', 500);
-- Si retorna FALSE → rechazar el upload con mensaje claro al usuario.
-- ============================================================
CREATE OR REPLACE FUNCTION org_can_upload(p_org_id UUID, p_new_rows INTEGER)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT (
    count_org_records(p_org_id) + p_new_rows
  ) <= (
    SELECT max_records FROM public.organizations WHERE id = p_org_id
  );
$$;

-- ============================================================
-- FUNCIÓN: Insertar en audit_log (wrapper para el backend)
-- El backend llama esta función con service_role_key.
-- Encapsula el INSERT para mantener la interfaz estable.
-- ============================================================
CREATE OR REPLACE FUNCTION log_action(
  p_org_id        UUID,
  p_user_id       UUID,
  p_action        TEXT,
  p_resource_type TEXT DEFAULT NULL,
  p_resource_id   UUID DEFAULT NULL,
  p_details       JSONB DEFAULT NULL,
  p_ip_address    INET DEFAULT NULL
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.audit_log (
    org_id, user_id, action, resource_type,
    resource_id, details, ip_address
  ) VALUES (
    p_org_id, p_user_id, p_action, p_resource_type,
    p_resource_id, p_details, p_ip_address
  );
END;
$$;

-- ============================================================
-- GRANTS: Permisos para roles de Supabase
-- authenticated: usuarios con JWT válido
-- anon: acceso no autenticado (para endpoints públicos)
-- ============================================================
GRANT USAGE ON SCHEMA public TO anon, authenticated;

-- organizations: leer y actualizar (RLS restringe a la org propia)
GRANT SELECT, UPDATE ON public.organizations TO authenticated;

-- profiles: leer, insertar y actualizar (RLS restringe al propio perfil)
GRANT SELECT, INSERT, UPDATE ON public.profiles TO authenticated;

-- uploaded_files: operaciones completas (soft delete via UPDATE deleted_at)
GRANT SELECT, INSERT, UPDATE ON public.uploaded_files TO authenticated;

-- data_records: solo lectura e inserción para usuarios (backend escribe en bulk)
GRANT SELECT, INSERT ON public.data_records TO authenticated;

-- agent_sessions: leer, insertar y actualizar estado
GRANT SELECT, INSERT, UPDATE ON public.agent_sessions TO authenticated;

-- agent_results: solo lectura (el backend ADK inserta con service_role)
GRANT SELECT ON public.agent_results TO authenticated;

-- dashboards: operaciones completas (soft delete via UPDATE deleted_at)
GRANT SELECT, INSERT, UPDATE ON public.dashboards TO authenticated;

-- widgets: operaciones completas incluido DELETE (no tiene soft delete)
GRANT SELECT, INSERT, UPDATE, DELETE ON public.widgets TO authenticated;

-- chat_messages: leer e insertar (no hay edición de mensajes)
GRANT SELECT, INSERT ON public.chat_messages TO authenticated;

-- audit_log: solo lectura para usuarios (INSERT via service_role o log_action())
GRANT SELECT ON public.audit_log TO authenticated;

-- Funciones utilitarias accesibles para usuarios autenticados
GRANT EXECUTE ON FUNCTION count_org_records(UUID) TO authenticated;
GRANT EXECUTE ON FUNCTION org_can_upload(UUID, INTEGER) TO authenticated;
