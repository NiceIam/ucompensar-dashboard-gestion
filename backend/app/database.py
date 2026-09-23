"""Gestor de conexiones PostgreSQL con soporte multi-database (una DB por org).

Usa asyncpg para operaciones async en FastAPI.
Cada organizacion tiene su propia base de datos: org_<uuid_sin_guiones>.
La base de datos principal 'pi_main' almacena usuarios y organizaciones.
"""

import asyncpg
import logging
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

_main_pool: Optional[asyncpg.Pool] = None
_org_pools: dict[str, asyncpg.Pool] = {}


# ---------------------------------------------------------------------------
# Pools
# ---------------------------------------------------------------------------

async def get_main_pool() -> asyncpg.Pool:
    """Pool de conexiones a la base de datos principal (pi_main)."""
    global _main_pool
    if _main_pool is None:
        s = get_settings()
        _main_pool = await asyncpg.create_pool(
            host=s.DATABASE_HOST,
            port=s.DATABASE_PORT,
            user=s.DATABASE_USER,
            password=s.DATABASE_PASSWORD,
            database=s.DATABASE_NAME,
            min_size=2,
            max_size=10,
        )
    return _main_pool


async def get_org_pool(org_id: str) -> asyncpg.Pool:
    """Pool de conexiones a la base de datos de una organizacion."""
    db_name = _org_db_name(org_id)
    if db_name not in _org_pools:
        s = get_settings()
        _org_pools[db_name] = await asyncpg.create_pool(
            host=s.DATABASE_HOST,
            port=s.DATABASE_PORT,
            user=s.DATABASE_USER,
            password=s.DATABASE_PASSWORD,
            database=db_name,
            min_size=1,
            max_size=5,
        )
    return _org_pools[db_name]


async def close_all_pools():
    """Cierra todos los pools (llamar en shutdown)."""
    global _main_pool
    if _main_pool:
        await _main_pool.close()
        _main_pool = None
    for pool in _org_pools.values():
        await pool.close()
    _org_pools.clear()


# ---------------------------------------------------------------------------
# Inicializacion de la BD principal
# ---------------------------------------------------------------------------

MAIN_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(120) NOT NULL,
    sector VARCHAR(50) DEFAULT 'comercio',
    size VARCHAR(20) DEFAULT 'pequeña',
    nit VARCHAR(20),
    city VARCHAR(50) DEFAULT 'Bogotá',
    business_type VARCHAR(50),
    plan_type VARCHAR(20) DEFAULT 'free',
    max_records INTEGER DEFAULT 10000,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    role VARCHAR(20) DEFAULT 'owner',
    phone VARCHAR(20),
    avatar_url VARCHAR(500),
    preferences JSONB DEFAULT '{}',
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS business_types (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    description TEXT,
    icon VARCHAR(50),
    schema_definition JSONB DEFAULT '{}',
    default_kpis JSONB DEFAULT '[]',
    default_dashboard_config JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""

SEED_BUSINESS_TYPES_SQL = """
INSERT INTO business_types (name, display_name, description, icon, schema_definition, default_kpis)
VALUES
(
    'ferreteria',
    'Ferretería / Retail',
    'Gestión de productos, inventario, ventas y proveedores',
    'Wrench',
    '{"tables": ["productos", "ventas", "proveedores", "inventario_movimientos"]}',
    '["ventas_totales", "productos_activos", "margen_promedio", "rotacion_inventario"]'
),
(
    'servicios',
    'Empresa de Servicios',
    'Gestión de servicios, clientes, cotizaciones y facturación',
    'Briefcase',
    '{"tables": ["servicios", "clientes", "cotizaciones", "facturas"]}',
    '["ingresos_totales", "clientes_activos", "cotizaciones_pendientes", "tasa_conversion"]'
),
(
    'restaurante',
    'Restaurante / Alimentos',
    'Gestión de menú, pedidos, inventario y proveedores',
    'UtensilsCrossed',
    '{"tables": ["menu_items", "pedidos", "inventario", "proveedores"]}',
    '["ventas_diarias", "platos_populares", "costo_ingredientes", "ticket_promedio"]'
)
ON CONFLICT (name) DO NOTHING;
"""


# ---------------------------------------------------------------------------
# Schema por tipo de negocio (tablas dentro de la DB de cada org)
# ---------------------------------------------------------------------------

ORG_BASE_SCHEMA_SQL = """
-- Metadatos de tablas de la org
CREATE TABLE IF NOT EXISTS org_data_tables (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_name VARCHAR(100) NOT NULL UNIQUE,
    display_name VARCHAR(150) NOT NULL,
    columns_definition JSONB DEFAULT '[]',
    row_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Filas de datos (JSONB flexible)
CREATE TABLE IF NOT EXISTS org_data_rows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_id UUID NOT NULL REFERENCES org_data_tables(id) ON DELETE CASCADE,
    data JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Archivos subidos
CREATE TABLE IF NOT EXISTS uploaded_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename VARCHAR(255) NOT NULL,
    original_name VARCHAR(255),
    mime_type VARCHAR(100),
    size_bytes INTEGER DEFAULT 0,
    rows_count INTEGER DEFAULT 0,
    columns_info JSONB DEFAULT '[]',
    file_data BYTEA,
    status VARCHAR(20) DEFAULT 'uploaded',
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Jobs ETL
CREATE TABLE IF NOT EXISTS etl_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id UUID REFERENCES uploaded_files(id),
    source_type VARCHAR(20),
    filename VARCHAR(255),
    target_table VARCHAR(100),
    status VARCHAR(20) DEFAULT 'pending',
    rows_extracted INTEGER DEFAULT 0,
    rows_loaded INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Sesiones de agentes
CREATE TABLE IF NOT EXISTS agent_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    file_id UUID,
    status VARCHAR(20) DEFAULT 'pending',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    gemini_tokens_used INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Resultados de agentes
CREATE TABLE IF NOT EXISTS agent_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES agent_sessions(id),
    agent_name VARCHAR(50),
    output JSONB DEFAULT '{}',
    execution_time_ms INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Mensajes de chat
CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Dashboards
CREATE TABLE IF NOT EXISTS dashboards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(120) NOT NULL,
    description TEXT,
    is_default BOOLEAN DEFAULT FALSE,
    is_public BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);

-- Widgets
CREATE TABLE IF NOT EXISTS widgets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dashboard_id UUID NOT NULL REFERENCES dashboards(id) ON DELETE CASCADE,
    title VARCHAR(120) NOT NULL,
    widget_type VARCHAR(30) NOT NULL,
    config JSONB DEFAULT '{}',
    position_x INTEGER DEFAULT 0,
    position_y INTEGER DEFAULT 0,
    width INTEGER DEFAULT 6,
    height INTEGER DEFAULT 4,
    data_source_query JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Registros de datos legacy (compatibilidad)
CREATE TABLE IF NOT EXISTS data_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_name VARCHAR(100),
    data JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
"""

# Tablas especificas por tipo de negocio
BUSINESS_TYPE_TABLES: dict[str, list[dict]] = {
    "ferreteria": [
        {
            "table_name": "productos",
            "display_name": "Productos",
            "columns_definition": [
                {"name": "nombre", "type": "text", "required": True},
                {"name": "categoria", "type": "text"},
                {"name": "precio_compra", "type": "number"},
                {"name": "precio_venta", "type": "number"},
                {"name": "stock", "type": "integer"},
                {"name": "proveedor", "type": "text"},
                {"name": "codigo", "type": "text"},
            ],
        },
        {
            "table_name": "ventas",
            "display_name": "Ventas",
            "columns_definition": [
                {"name": "fecha", "type": "date", "required": True},
                {"name": "producto", "type": "text", "required": True},
                {"name": "cantidad", "type": "integer", "required": True},
                {"name": "precio_unitario", "type": "number"},
                {"name": "total", "type": "number"},
                {"name": "cliente", "type": "text"},
                {"name": "metodo_pago", "type": "text"},
            ],
        },
        {
            "table_name": "proveedores",
            "display_name": "Proveedores",
            "columns_definition": [
                {"name": "nombre", "type": "text", "required": True},
                {"name": "contacto", "type": "text"},
                {"name": "telefono", "type": "text"},
                {"name": "email", "type": "text"},
                {"name": "direccion", "type": "text"},
                {"name": "productos_suministrados", "type": "text"},
            ],
        },
        {
            "table_name": "inventario_movimientos",
            "display_name": "Movimientos de Inventario",
            "columns_definition": [
                {"name": "fecha", "type": "date", "required": True},
                {"name": "producto", "type": "text", "required": True},
                {"name": "tipo_movimiento", "type": "text", "required": True},
                {"name": "cantidad", "type": "integer", "required": True},
                {"name": "motivo", "type": "text"},
            ],
        },
    ],
    "servicios": [
        {
            "table_name": "servicios",
            "display_name": "Servicios",
            "columns_definition": [
                {"name": "nombre", "type": "text", "required": True},
                {"name": "descripcion", "type": "text"},
                {"name": "precio_base", "type": "number"},
                {"name": "duracion_horas", "type": "number"},
                {"name": "categoria", "type": "text"},
            ],
        },
        {
            "table_name": "clientes",
            "display_name": "Clientes",
            "columns_definition": [
                {"name": "nombre", "type": "text", "required": True},
                {"name": "empresa", "type": "text"},
                {"name": "email", "type": "text"},
                {"name": "telefono", "type": "text"},
                {"name": "ciudad", "type": "text"},
            ],
        },
        {
            "table_name": "cotizaciones",
            "display_name": "Cotizaciones",
            "columns_definition": [
                {"name": "fecha", "type": "date", "required": True},
                {"name": "cliente", "type": "text", "required": True},
                {"name": "servicio", "type": "text", "required": True},
                {"name": "valor", "type": "number"},
                {"name": "estado", "type": "text"},
            ],
        },
        {
            "table_name": "facturas",
            "display_name": "Facturas",
            "columns_definition": [
                {"name": "numero", "type": "text", "required": True},
                {"name": "fecha", "type": "date", "required": True},
                {"name": "cliente", "type": "text", "required": True},
                {"name": "subtotal", "type": "number"},
                {"name": "iva", "type": "number"},
                {"name": "total", "type": "number"},
                {"name": "estado_pago", "type": "text"},
            ],
        },
    ],
    "restaurante": [
        {
            "table_name": "menu_items",
            "display_name": "Menú",
            "columns_definition": [
                {"name": "nombre", "type": "text", "required": True},
                {"name": "categoria", "type": "text"},
                {"name": "precio", "type": "number", "required": True},
                {"name": "costo", "type": "number"},
                {"name": "disponible", "type": "boolean"},
            ],
        },
        {
            "table_name": "pedidos",
            "display_name": "Pedidos",
            "columns_definition": [
                {"name": "fecha", "type": "date", "required": True},
                {"name": "mesa", "type": "text"},
                {"name": "items", "type": "text", "required": True},
                {"name": "total", "type": "number"},
                {"name": "metodo_pago", "type": "text"},
                {"name": "mesero", "type": "text"},
            ],
        },
        {
            "table_name": "inventario",
            "display_name": "Inventario",
            "columns_definition": [
                {"name": "ingrediente", "type": "text", "required": True},
                {"name": "cantidad", "type": "number"},
                {"name": "unidad", "type": "text"},
                {"name": "costo_unitario", "type": "number"},
                {"name": "minimo_stock", "type": "number"},
            ],
        },
        {
            "table_name": "proveedores",
            "display_name": "Proveedores",
            "columns_definition": [
                {"name": "nombre", "type": "text", "required": True},
                {"name": "contacto", "type": "text"},
                {"name": "telefono", "type": "text"},
                {"name": "productos", "type": "text"},
            ],
        },
    ],
}


async def init_main_db():
    """Inicializa las tablas de la base de datos principal."""
    pool = await get_main_pool()
    async with pool.acquire() as conn:
        await conn.execute(MAIN_SCHEMA_SQL)
        await conn.execute(SEED_BUSINESS_TYPES_SQL)
    logger.info("Base de datos principal inicializada.")


async def create_org_database(org_id: str, business_type: str = "ferreteria"):
    """Crea una base de datos dedicada para la organizacion e inicializa su schema."""
    db_name = _org_db_name(org_id)
    s = get_settings()

    # Crear la BD (no puede estar dentro de una transaccion)
    conn = await asyncpg.connect(
        host=s.DATABASE_HOST,
        port=s.DATABASE_PORT,
        user=s.DATABASE_USER,
        password=s.DATABASE_PASSWORD,
        database=s.DATABASE_NAME,
    )
    try:
        # Verificar si ya existe
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", db_name
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{db_name}"')
            logger.info(f"Base de datos creada: {db_name}")
    finally:
        await conn.close()

    # Inicializar schema de la org
    pool = await get_org_pool(org_id)
    async with pool.acquire() as conn:
        await conn.execute(ORG_BASE_SCHEMA_SQL)
        await _dedupe_org_data_tables(conn)

        # Insertar tablas del tipo de negocio
        tables = BUSINESS_TYPE_TABLES.get(business_type, [])
        import json
        for table_def in tables:
            await conn.execute(
                """
                INSERT INTO org_data_tables (table_name, display_name, columns_definition)
                VALUES ($1, $2, $3::jsonb)
                ON CONFLICT (table_name) DO NOTHING
                """,
                table_def["table_name"],
                table_def["display_name"],
                json.dumps(table_def["columns_definition"]),
            )

    logger.info(f"Schema org inicializado: {db_name} (tipo: {business_type})")


async def _dedupe_org_data_tables(conn) -> None:
    """Auto-repara BDs de org creadas antes de que `table_name` fuera UNIQUE.

    `ORG_BASE_SCHEMA_SQL` usa CREATE TABLE IF NOT EXISTS, asi que agregar la
    restriccion UNIQUE no se aplica retroactivamente a BDs ya existentes con
    filas duplicadas (bug: el INSERT de mas abajo usaba `ON CONFLICT DO
    NOTHING` sin un target real, que no evita duplicados sin la constraint).
    Esta funcion fusiona duplicados por table_name -- reasigna org_data_rows
    hacia la copia con mas datos (nunca borra filas de datos, solo la
    metadata duplicada) -- y luego agrega la restriccion si aun falta.
    """
    async with conn.transaction():
        await conn.execute(
            """
            WITH ranked AS (
                SELECT id, table_name,
                       row_number() OVER (
                           PARTITION BY table_name
                           ORDER BY row_count DESC, created_at ASC
                       ) AS rn
                FROM org_data_tables
            ),
            keepers AS (
                SELECT table_name, id AS keeper_id FROM ranked WHERE rn = 1
            ),
            losers AS (
                SELECT r.id AS loser_id, k.keeper_id
                FROM ranked r
                JOIN keepers k ON k.table_name = r.table_name
                WHERE r.rn > 1
            )
            UPDATE org_data_rows
            SET table_id = losers.keeper_id
            FROM losers
            WHERE org_data_rows.table_id = losers.loser_id
            """
        )
        await conn.execute(
            """
            WITH ranked AS (
                SELECT id,
                       row_number() OVER (
                           PARTITION BY table_name
                           ORDER BY row_count DESC, created_at ASC
                       ) AS rn
                FROM org_data_tables
            )
            DELETE FROM org_data_tables WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
            """
        )
        await conn.execute(
            """
            UPDATE org_data_tables t
            SET row_count = (SELECT count(*) FROM org_data_rows r WHERE r.table_id = t.id)
            """
        )
        try:
            await conn.execute(
                "ALTER TABLE org_data_tables ADD CONSTRAINT org_data_tables_table_name_key UNIQUE (table_name)"
            )
        except (asyncpg.exceptions.DuplicateObjectError, asyncpg.exceptions.DuplicateTableError):
            # Ya existe -- BD nueva (UNIQUE inline en ORG_BASE_SCHEMA_SQL genera
            # automaticamente una restriccion con este mismo nombre), o una BD
            # vieja a la que ya se le aplico este fix antes.
            pass


def _org_db_name(org_id: str) -> str:
    """Genera el nombre de la BD de una org."""
    return f"org_{org_id.replace('-', '_')}"


def get_sync_dsn(org_id: str) -> str:
    """DSN sincrono para psycopg2 (usado por los agentes)."""
    s = get_settings()
    db_name = _org_db_name(org_id)
    return f"postgresql://{s.DATABASE_USER}:{s.DATABASE_PASSWORD}@{s.DATABASE_HOST}:{s.DATABASE_PORT}/{db_name}"


def get_main_sync_dsn() -> str:
    """DSN sincrono para la BD principal."""
    s = get_settings()
    return f"postgresql://{s.DATABASE_USER}:{s.DATABASE_PASSWORD}@{s.DATABASE_HOST}:{s.DATABASE_PORT}/{s.DATABASE_NAME}"
