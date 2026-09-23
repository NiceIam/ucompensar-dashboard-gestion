-- ============================================================
-- PI0320251 — Solución WEB para la gestión estratégica de datos con IA
-- Fundación Universitaria Ucompensar — Grupo GIIS / Semillero Data Core Tech
--
-- Migration: 00003_seed_data.sql
-- Datos de prueba para desarrollo local y validación del prototipo
--
-- ADVERTENCIA: Este archivo es SOLO para entorno de desarrollo.
-- NO ejecutar en producción.
-- Las 2 organizaciones representan los pilotos mínimos requeridos:
--   1. Sector terciario (comercio/servicios)
--   2. Sector TIC
-- ============================================================

-- ============================================================
-- ORGANIZACIONES DE PRUEBA
-- UUIDs fijos para facilitar referencias cruzadas en pruebas
-- ============================================================

-- Organización 1: Comercio minorista (sector terciario)
-- Piloto: empresa de servicios/comercio en Bogotá
INSERT INTO public.organizations (
  id,
  name,
  sector,
  size,
  nit,
  city,
  plan_type,
  max_records
) VALUES (
  'a1000000-0000-0000-0000-000000000001',
  'Distribuciones Bogotá SAS',
  'comercio',
  'pequeña',
  '900123456-7',
  'Bogotá',
  'free',
  10000
);

-- Organización 2: Empresa de tecnología (sector TIC)
-- Piloto: empresa TIC en Bogotá
INSERT INTO public.organizations (
  id,
  name,
  sector,
  size,
  nit,
  city,
  plan_type,
  max_records
) VALUES (
  'b2000000-0000-0000-0000-000000000002',
  'TechSoluciones Colombia SAS',
  'TIC',
  'micro',
  '900987654-3',
  'Bogotá',
  'free',
  10000
);

-- ============================================================
-- USUARIOS DE PRUEBA (profiles)
--
-- NOTA: En Supabase, los profiles se crean automáticamente via
-- el trigger handle_new_user() cuando se registra un usuario en auth.users.
-- Para entorno local (supabase start), crear manualmente con UUIDs fijos.
--
-- Los auth.users deben crearse primero via Supabase Auth Admin API
-- o via el dashboard local: http://localhost:54323
--
-- UUIDs de usuarios de prueba (deben existir en auth.users antes de insertar):
-- User 1: c3000000-0000-0000-0000-000000000003 → owner de org 1
-- User 2: d4000000-0000-0000-0000-000000000004 → admin de org 1
-- User 3: e5000000-0000-0000-0000-000000000005 → owner de org 2
--
-- Para crear en entorno local, usar la Supabase Management API:
--   POST http://localhost:54321/auth/v1/admin/users
--   { "email": "...", "password": "...", "email_confirm": true }
-- ============================================================

-- Perfil de prueba — owner de Distribuciones Bogotá SAS
-- Descomentar solo si el auth.users correspondiente ya fue creado
/*
INSERT INTO public.profiles (id, org_id, full_name, role, email)
VALUES (
  'c3000000-0000-0000-0000-000000000003',
  'a1000000-0000-0000-0000-000000000001',
  'Carlos Distribuciones',
  'owner',
  'carlos.test@distribuciones-bogota.co'
);
*/

-- Perfil de prueba — admin de Distribuciones Bogotá SAS
/*
INSERT INTO public.profiles (id, org_id, full_name, role, email)
VALUES (
  'd4000000-0000-0000-0000-000000000004',
  'a1000000-0000-0000-0000-000000000001',
  'Ana Analista',
  'admin',
  'ana.test@distribuciones-bogota.co'
);
*/

-- Perfil de prueba — owner de TechSoluciones Colombia SAS
/*
INSERT INTO public.profiles (id, org_id, full_name, role, email)
VALUES (
  'e5000000-0000-0000-0000-000000000005',
  'b2000000-0000-0000-0000-000000000002',
  'Juan TechSoluciones',
  'owner',
  'juan.test@techsoluciones.co'
);
*/

-- ============================================================
-- VERIFICACIÓN POST-SEED
-- Ejecutar manualmente para confirmar que los datos se insertaron
-- ============================================================

-- SELECT id, name, sector, size, plan_type FROM public.organizations;
-- SELECT id, org_id, full_name, role, email FROM public.profiles;

-- ============================================================
-- LIMPIEZA (para resetear el entorno de desarrollo)
-- Ejecutar manualmente si se necesita reiniciar el estado
-- ============================================================

-- DELETE FROM public.audit_log WHERE org_id IN (
--   'a1000000-0000-0000-0000-000000000001',
--   'b2000000-0000-0000-0000-000000000002'
-- );
-- DELETE FROM public.chat_messages WHERE org_id IN (
--   'a1000000-0000-0000-0000-000000000001',
--   'b2000000-0000-0000-0000-000000000002'
-- );
-- DELETE FROM public.widgets WHERE org_id IN (
--   'a1000000-0000-0000-0000-000000000001',
--   'b2000000-0000-0000-0000-000000000002'
-- );
-- DELETE FROM public.dashboards WHERE org_id IN (
--   'a1000000-0000-0000-0000-000000000001',
--   'b2000000-0000-0000-0000-000000000002'
-- );
-- DELETE FROM public.agent_results WHERE org_id IN (
--   'a1000000-0000-0000-0000-000000000001',
--   'b2000000-0000-0000-0000-000000000002'
-- );
-- DELETE FROM public.agent_sessions WHERE org_id IN (
--   'a1000000-0000-0000-0000-000000000001',
--   'b2000000-0000-0000-0000-000000000002'
-- );
-- DELETE FROM public.data_records WHERE org_id IN (
--   'a1000000-0000-0000-0000-000000000001',
--   'b2000000-0000-0000-0000-000000000002'
-- );
-- DELETE FROM public.uploaded_files WHERE org_id IN (
--   'a1000000-0000-0000-0000-000000000001',
--   'b2000000-0000-0000-0000-000000000002'
-- );
-- DELETE FROM public.profiles WHERE org_id IN (
--   'a1000000-0000-0000-0000-000000000001',
--   'b2000000-0000-0000-0000-000000000002'
-- );
-- DELETE FROM public.organizations WHERE id IN (
--   'a1000000-0000-0000-0000-000000000001',
--   'b2000000-0000-0000-0000-000000000002'
-- );
