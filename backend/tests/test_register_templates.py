"""Registro de organizaciones: sin hojas de plantilla por defecto — PI0320251.

Bug: `register_organization` mapeaba `sector` a un pack de plantillas con una lista (ferreteria/servicios/
restaurante) que NUNCA coincide con los sectores del formulario (terciario, cuaternario, TIC, salud, educacion,
comercio), asi que a TODAS las organizaciones se les creaban las hojas vacias de "servicios".
Decision: la organizacion nace vacia; las plantillas solo existen si la persona elige un tipo de negocio
(POST /api/v1/templates/initialize).
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.schemas import UserRegister
from app.services import auth_service
from tests.test_auth_service import _make_pool_conn

SECTORES_DEL_FORMULARIO = ["terciario", "cuaternario", "TIC", "salud", "educacion", "comercio"]


def _body(sector):
    return UserRegister(email="nuevo@ejemplo.com", password="SuperSecret123!", full_name="Nuevo Usuario",
                        org_name="Mi Empresa S.A.S", sector=sector, size="pequeña", city="Bogotá")


async def _registrar(sector):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(side_effect=[{"id": "org-uuid", "name": "x"}, {"id": "user-uuid"}])
    conn.fetchval = AsyncMock(return_value=None)
    conn.execute = AsyncMock()
    create_db = AsyncMock()
    with patch("app.services.auth_service.get_main_pool", AsyncMock(return_value=_make_pool_conn(conn))), \
            patch("app.services.auth_service.create_org_database", create_db):
        await auth_service.register_organization(_body(sector))
    return create_db


@pytest.mark.parametrize("sector", SECTORES_DEL_FORMULARIO)
async def test_ningun_sector_del_formulario_crea_plantillas(sector):
    create_db = await _registrar(sector)
    create_db.assert_awaited_once()
    assert create_db.await_args.args == ("org-uuid", None)


class _FakeAdmin:
    async def fetchval(self, *a):
        return 1          # la base ya existe

    async def execute(self, *a):
        pass

    async def close(self):
        pass


def _fake_org_pool(inserted):
    conn = MagicMock()

    async def execute(sql, *args):
        if "INSERT INTO org_data_tables" in sql:
            inserted.append(args[0])

    conn.execute = execute
    conn.transaction = MagicMock()
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return AsyncMock(return_value=pool)


@pytest.mark.parametrize("business_type,expected", [
    (None, []),
    ("servicios", ["servicios", "clientes", "cotizaciones", "facturas"]),
    ("restaurante", ["menu_items", "pedidos", "inventario", "proveedores"]),
    ("ferreteria", ["productos", "ventas", "proveedores", "inventario_movimientos"]),
    ("sector_inventado", []),
])
async def test_create_org_database_solo_crea_plantillas_del_tipo_elegido(business_type, expected):
    from app import database

    inserted: list[str] = []
    with patch("app.database.asyncpg.connect", AsyncMock(return_value=_FakeAdmin())), \
            patch("app.database.get_org_pool", _fake_org_pool(inserted)), \
            patch("app.database._dedupe_org_data_tables", AsyncMock()):
        await database.create_org_database("550e8400-e29b-41d4-a716-446655440000", business_type)
    assert inserted == expected


async def test_el_endpoint_de_plantillas_sigue_creando_las_del_tipo_elegido():
    """initialize_org_schema es el UNICO camino a plantillas: pasa el nombre del tipo elegido, no el sector."""
    from app.services import template_service

    main_conn = AsyncMock()
    main_conn.fetchrow = AsyncMock(return_value={"id": "bt", "name": "restaurante", "display_name": "Restaurante",
                                                 "schema_definition": "{}"})
    main_conn.execute = AsyncMock()
    org_conn = AsyncMock()
    org_conn.fetch = AsyncMock(return_value=[])
    create_db = AsyncMock()
    with patch("app.services.template_service.get_main_pool", AsyncMock(return_value=_make_pool_conn(main_conn))), \
            patch("app.services.template_service.create_org_database", create_db), \
            patch("app.services.template_service.get_org_pool", AsyncMock(return_value=_make_pool_conn(org_conn))):
        await template_service.initialize_org_schema("org-1", "bt")
    assert create_db.await_args.args == ("org-1", "restaurante")
