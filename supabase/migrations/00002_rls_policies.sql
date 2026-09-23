-- ============================================================
-- PI0320251 — Solución WEB para la gestión estratégica de datos con IA
-- Fundación Universitaria Ucompensar — Grupo GIIS / Semillero Data Core Tech
--
-- Migration: 00002_rls_policies.sql
-- Row Level Security — aislamiento multi-tenant estricto
-- Principio: cada empresa es una isla de datos
-- ============================================================

-- ============================================================
-- HELPER: obtener org_id del usuario autenticado
--
-- SECURITY DEFINER es obligatorio para evitar recursión infinita:
-- sin él, la evaluación de RLS en profiles dispararía otra evaluación
-- de RLS en profiles → loop infinito.
--
-- El fallback a app.org_id permite al backend (FastAPI con service_role)
-- establecer el contexto de org via SET LOCAL app.org_id = '...'
-- en una transacción, manteniendo el aislamiento sin bypass de RLS.
-- ============================================================
CREATE OR REPLACE FUNCTION get_user_org_id()
RETURNS UUID
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_org_id_text TEXT;
BEGIN
  -- Intenta obtener org_id de una variable de sesión (para el backend con service_role)
  v_org_id_text := current_setting('app.org_id', true);
  IF v_org_id_text IS NOT NULL AND v_org_id_text <> '' THEN
    RETURN v_org_id_text::UUID;
  END IF;

  -- Fallback: leer desde profiles del usuario autenticado con Supabase Auth
  -- app_metadata no es editable por el usuario desde el cliente
  RETURN (
    SELECT org_id FROM public.profiles WHERE id = auth.uid()
  );
END;
$$;

-- ============================================================
-- HELPER: obtener role del usuario autenticado
-- Permite crear políticas RLS que diferencian por rol (owner/admin/viewer).
-- SECURITY DEFINER por la misma razón que get_user_org_id().
-- ============================================================
CREATE OR REPLACE FUNCTION get_user_role()
RETURNS TEXT
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT role FROM public.profiles WHERE id = auth.uid();
$$;

-- Grants para las funciones helper
GRANT EXECUTE ON FUNCTION get_user_org_id() TO authenticated;
GRANT EXECUTE ON FUNCTION get_user_role() TO authenticated;

-- ============================================================
-- HABILITAR RLS EN TODAS LAS TABLAS
-- Ninguna tabla queda expuesta sin filtro de tenant.
-- ============================================================
ALTER TABLE public.organizations  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profiles       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.uploaded_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.data_records   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_results  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.dashboards     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.widgets        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_messages  ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_log      ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- POLÍTICAS: organizations
--
-- SELECT: cualquier miembro de la org puede ver su organización
-- UPDATE: solo owner/admin pueden modificar datos de la org
-- INSERT: lo hace el sistema (handle_new_user) — no hay política INSERT
--         para usuarios directos, bloqueando creación manual
-- DELETE: sin política DELETE = nadie puede borrar orgs desde el cliente
-- ============================================================
CREATE POLICY "org_read"
  ON public.organizations
  FOR SELECT
  USING (id = get_user_org_id());

CREATE POLICY "org_update_owner_admin"
  ON public.organizations
  FOR UPDATE
  USING (
    id = get_user_org_id()
    AND get_user_role() IN ('owner', 'admin')
  )
  WITH CHECK (
    id = get_user_org_id()
    AND get_user_role() IN ('owner', 'admin')
  );

-- ============================================================
-- POLÍTICAS: profiles
--
-- SELECT: cualquier miembro de la org puede ver los perfiles de su org
-- INSERT: solo para tu propio perfil (id = auth.uid())
-- UPDATE (self): cualquier usuario puede actualizar su propio perfil
-- UPDATE (admin): owner/admin puede actualizar roles de otros miembros de la org
-- ============================================================
CREATE POLICY "profiles_org_select"
  ON public.profiles
  FOR SELECT
  USING (org_id = get_user_org_id());

CREATE POLICY "profiles_self_insert"
  ON public.profiles
  FOR INSERT
  WITH CHECK (id = auth.uid());

CREATE POLICY "profiles_self_update"
  ON public.profiles
  FOR UPDATE
  USING (id = auth.uid())
  WITH CHECK (id = auth.uid());

-- Owner/admin puede actualizar roles de otros usuarios en su misma org
CREATE POLICY "profiles_admin_update_role"
  ON public.profiles
  FOR UPDATE
  USING (
    org_id = get_user_org_id()
    AND get_user_role() IN ('owner', 'admin')
  )
  WITH CHECK (
    org_id = get_user_org_id()
    AND get_user_role() IN ('owner', 'admin')
  );

-- ============================================================
-- POLÍTICAS: uploaded_files
--
-- SELECT: solo archivos activos (deleted_at IS NULL) de la propia org
-- INSERT: cualquier miembro de la org puede subir archivos
-- UPDATE: cualquier miembro puede actualizar metadatos (status, etc.)
--         El soft delete (deleted_at) se hace con UPDATE — no con DELETE
-- No hay política DELETE: los archivos no se eliminan físicamente
-- ============================================================
CREATE POLICY "uploaded_files_org_select"
  ON public.uploaded_files
  FOR SELECT
  USING (org_id = get_user_org_id() AND deleted_at IS NULL);

CREATE POLICY "uploaded_files_org_insert"
  ON public.uploaded_files
  FOR INSERT
  WITH CHECK (org_id = get_user_org_id());

CREATE POLICY "uploaded_files_org_update"
  ON public.uploaded_files
  FOR UPDATE
  USING (org_id = get_user_org_id())
  WITH CHECK (org_id = get_user_org_id());

-- ============================================================
-- POLÍTICAS: data_records
--
-- SELECT: cualquier miembro de la org puede leer sus registros
-- INSERT: el backend (FastAPI) inserta en bulk — también aplica a service_role
-- No hay políticas UPDATE/DELETE: se hace solo vía FastAPI con service_role,
-- nunca expuesto directamente al usuario del cliente
-- ============================================================
CREATE POLICY "data_records_org_select"
  ON public.data_records
  FOR SELECT
  USING (org_id = get_user_org_id());

CREATE POLICY "data_records_org_insert"
  ON public.data_records
  FOR INSERT
  WITH CHECK (org_id = get_user_org_id());

-- ============================================================
-- POLÍTICAS: agent_sessions
--
-- SELECT: cualquier miembro puede ver el historial de sesiones de su org
-- INSERT: el backend inicia sesiones en nombre del usuario
-- UPDATE: el backend actualiza el status durante la ejecución del pipeline
-- ============================================================
CREATE POLICY "agent_sessions_org_select"
  ON public.agent_sessions
  FOR SELECT
  USING (org_id = get_user_org_id());

CREATE POLICY "agent_sessions_org_insert"
  ON public.agent_sessions
  FOR INSERT
  WITH CHECK (org_id = get_user_org_id());

CREATE POLICY "agent_sessions_org_update"
  ON public.agent_sessions
  FOR UPDATE
  USING (org_id = get_user_org_id())
  WITH CHECK (org_id = get_user_org_id());

-- ============================================================
-- POLÍTICAS: agent_results
--
-- SELECT: cualquier miembro puede ver los resultados de los agentes
-- INSERT: el backend ADK inserta resultados (también con service_role)
-- No hay UPDATE: los resultados son inmutables una vez escritos
-- ============================================================
CREATE POLICY "agent_results_org_select"
  ON public.agent_results
  FOR SELECT
  USING (org_id = get_user_org_id());

CREATE POLICY "agent_results_org_insert"
  ON public.agent_results
  FOR INSERT
  WITH CHECK (org_id = get_user_org_id());

-- ============================================================
-- POLÍTICAS: dashboards
--
-- SELECT: solo dashboards activos (deleted_at IS NULL) de la propia org
-- INSERT: cualquier miembro puede crear dashboards
-- UPDATE: cualquier miembro puede modificar dashboards (edición interactiva)
--         El soft delete se hace con UPDATE — no con DELETE
-- No hay política DELETE: soft delete vía UPDATE deleted_at
-- ============================================================
CREATE POLICY "dashboards_org_select"
  ON public.dashboards
  FOR SELECT
  USING (org_id = get_user_org_id() AND deleted_at IS NULL);

CREATE POLICY "dashboards_org_insert"
  ON public.dashboards
  FOR INSERT
  WITH CHECK (org_id = get_user_org_id());

CREATE POLICY "dashboards_org_update"
  ON public.dashboards
  FOR UPDATE
  USING (org_id = get_user_org_id())
  WITH CHECK (org_id = get_user_org_id());

-- ============================================================
-- POLÍTICAS: widgets
--
-- SELECT: cualquier miembro puede ver los widgets de su org
-- INSERT: cualquier miembro puede añadir widgets
-- UPDATE: cualquier miembro puede modificar widgets
-- DELETE: cualquier miembro puede eliminar widgets (sin soft delete en widgets)
-- ============================================================
CREATE POLICY "widgets_org_select"
  ON public.widgets
  FOR SELECT
  USING (org_id = get_user_org_id());

CREATE POLICY "widgets_org_insert"
  ON public.widgets
  FOR INSERT
  WITH CHECK (org_id = get_user_org_id());

CREATE POLICY "widgets_org_update"
  ON public.widgets
  FOR UPDATE
  USING (org_id = get_user_org_id())
  WITH CHECK (org_id = get_user_org_id());

CREATE POLICY "widgets_org_delete"
  ON public.widgets
  FOR DELETE
  USING (org_id = get_user_org_id());

-- ============================================================
-- POLÍTICAS: chat_messages
--
-- SELECT: usuarios solo ven sus PROPIOS mensajes (no los de otros de la org)
--         Privacidad del historial de chat — no es compartido por la org
-- INSERT: solo para tu propio user_id — no puedes insertar mensajes de otros
--
-- El chatbot (assistant) inserta mensajes con el user_id del usuario propietario
-- desde el backend con service_role, pero el filtro org + user_id sigue aplicando
-- ============================================================
CREATE POLICY "chat_messages_own_select"
  ON public.chat_messages
  FOR SELECT
  USING (
    org_id = get_user_org_id()
    AND user_id = auth.uid()
  );

CREATE POLICY "chat_messages_own_insert"
  ON public.chat_messages
  FOR INSERT
  WITH CHECK (
    org_id = get_user_org_id()
    AND user_id = auth.uid()
  );

-- ============================================================
-- POLÍTICAS: audit_log
--
-- SELECT: solo owner/admin pueden ver el log completo de su org
--         Los viewers no tienen acceso a la auditoría
-- INSERT: NO se define política INSERT para usuarios del cliente.
--         El backend usa service_role (bypass RLS) o la función log_action()
--         para escribir en el audit_log — nunca desde el frontend.
-- ============================================================
CREATE POLICY "audit_log_org_select"
  ON public.audit_log
  FOR SELECT
  USING (
    org_id = get_user_org_id()
    AND get_user_role() IN ('owner', 'admin')
  );

-- No hay política INSERT: escritura exclusiva via service_role o log_action()
