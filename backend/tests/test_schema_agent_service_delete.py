"""Unit tests de borrado en schema_agent_service y router /schema — PI0320251.

Contexto: delete_table tuvo un bug critico (DELETE ... RETURNING count(*) es SQL
invalido en Postgres y el borrado de tablas no funcionaba). La BD emulada
(tests/fake_org_db.py) rechaza agregaciones en RETURNING igual que Postgres, y
estos tests verifican ademas:
- que el DELETE solo toca la tabla/fila pedida (WHERE correcto)
- aislamiento multi-tenant: el org_id decide la BD; ids de otra org no se tocan
- atomicidad del borrado
- delete_row, que vive en app/routers/schema.py (no en el servicio)
"""

import os
import re
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.fake_org_db import FakeOrgDBs

os.environ.setdefault("DATABASE_HOST", "localhost")
os.environ.setdefault("DATABASE_PORT", "5432")
os.environ.setdefault("DATABASE_USER", "postgres")
os.environ.setdefault("DATABASE_PASSWORD", "postgres")
os.environ.setdefault("DATABASE_NAME", "pi_main")
os.environ.setdefault("GOOGLE_API_KEY", "test-google-api-key")
os.environ.setdefault("APP_SECRET_KEY", "test-app-secret-key-at-least-32-chars-ok")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("BCRYPT_ROUNDS", "10")

ORG_A = "550e8400-e29b-41d4-a716-446655440000"
ORG_B = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"


@pytest.fixture
def org_dbs():
    """FakeOrgDBs instalado como get_org_pool del servicio Y del router (import perezoso)."""
    dbs = FakeOrgDBs()
    with patch("app.services.schema_agent_service.get_org_pool", dbs.get_org_pool), \
         patch("app.database.get_org_pool", dbs.get_org_pool):
        yield dbs


def _user(org_id: str):
    return SimpleNamespace(org_id=org_id)


def _seed_two_tables(db):
    """Dos tablas en la misma org, con filas y registros legacy cada una."""
    victima = db.add_table("ventas", ["a"], rows=[{"a": i} for i in range(3)], legacy_records=3)
    intacta = db.add_table("clientes", ["b"], rows=[{"b": i} for i in range(4)], legacy_records=4)
    return victima, intacta


# ---------------------------------------------------------------------------
# delete_table
# ---------------------------------------------------------------------------

class TestDeleteTable:
    @pytest.mark.asyncio
    async def test_borra_tabla_filas_y_registros_legacy(self, org_dbs):
        from app.services.schema_agent_service import delete_table

        db = org_dbs.db(ORG_A)
        victima, _ = _seed_two_tables(db)

        result = await delete_table(ORG_A, str(victima))

        assert result == {"table_name": "ventas", "display_name": "Ventas", "rows_deleted": 3}
        assert victima not in db.tables
        assert db.rows_of(victima) == []
        assert not [r for r in db.records if r["table_name"] == "ventas"]

    @pytest.mark.asyncio
    async def test_no_toca_otras_tablas_de_la_misma_org(self, org_dbs):
        """Un DELETE sin WHERE correcto (el bug clasico) borraria tambien 'clientes'."""
        from app.services.schema_agent_service import delete_table

        db = org_dbs.db(ORG_A)
        victima, intacta = _seed_two_tables(db)

        await delete_table(ORG_A, str(victima))

        assert intacta in db.tables
        assert db.tables[intacta]["row_count"] == 4
        assert len(db.rows_of(intacta)) == 4
        assert len([r for r in db.records if r["table_name"] == "clientes"]) == 4

    @pytest.mark.asyncio
    async def test_todos_los_delete_llevan_where(self, org_dbs):
        from app.services.schema_agent_service import delete_table

        db = org_dbs.db(ORG_A)
        victima, _ = _seed_two_tables(db)

        await delete_table(ORG_A, str(victima))

        deletes = [q for q in db.sql_log if q.startswith("delete")]
        assert len(deletes) >= 3
        assert all(" where " in q for q in deletes)

    @pytest.mark.asyncio
    async def test_sql_de_borrado_no_usa_agregaciones_en_returning(self, org_dbs):
        """Regresion directa del bug historico: Postgres rechaza count(*) en RETURNING."""
        from app.services.schema_agent_service import delete_table

        db = org_dbs.db(ORG_A)
        victima, _ = _seed_two_tables(db)

        await delete_table(ORG_A, str(victima))

        for q in db.sql_log:
            if " returning " in q:
                assert not re.search(r"\b(count|sum|avg|min|max)\s*\(", q.split(" returning ", 1)[1])

    @pytest.mark.asyncio
    async def test_conteo_exacto_con_muchas_filas(self, org_dbs):
        from app.services.schema_agent_service import delete_table

        db = org_dbs.db(ORG_A)
        tid = db.add_table("grande", ["a"], rows=[{"a": i} for i in range(1500)])

        result = await delete_table(ORG_A, str(tid))

        assert result["rows_deleted"] == 1500

    @pytest.mark.asyncio
    async def test_tabla_vacia(self, org_dbs):
        from app.services.schema_agent_service import delete_table

        db = org_dbs.db(ORG_A)
        tid = db.add_table("vacia", ["a"])

        result = await delete_table(ORG_A, str(tid))

        assert result["rows_deleted"] == 0
        assert tid not in db.tables

    @pytest.mark.asyncio
    async def test_tabla_inexistente_no_borra_nada(self, org_dbs):
        from app.services.schema_agent_service import delete_table

        db = org_dbs.db(ORG_A)
        _seed_two_tables(db)

        result = await delete_table(ORG_A, str(uuid.uuid4()))

        assert result == {"error": "Tabla no encontrada"}
        assert len(db.tables) == 2
        assert len(db.rows) == 7
        assert len(db.records) == 7

    @pytest.mark.asyncio
    async def test_borrar_dos_veces_la_segunda_es_error(self, org_dbs):
        from app.services.schema_agent_service import delete_table

        tid = org_dbs.db(ORG_A).add_table("t", ["a"], rows=[{"a": 1}])

        await delete_table(ORG_A, str(tid))
        segunda = await delete_table(ORG_A, str(tid))

        assert segunda == {"error": "Tabla no encontrada"}

    # -- aislamiento por organizacion ----------------------------------------

    @pytest.mark.asyncio
    async def test_aislamiento_otra_org_no_puede_borrar_mi_tabla(self, org_dbs):
        """ORG_A pide borrar un table_id que pertenece a ORG_B: error y ORG_B intacta."""
        from app.services.schema_agent_service import delete_table

        db_b = org_dbs.db(ORG_B)
        tid_b = db_b.add_table("ventas", ["a"], rows=[{"a": 1}, {"a": 2}], legacy_records=2)
        org_dbs.db(ORG_A)

        result = await delete_table(ORG_A, str(tid_b))

        assert result == {"error": "Tabla no encontrada"}
        assert tid_b in db_b.tables
        assert len(db_b.rows_of(tid_b)) == 2
        assert len(db_b.records) == 2
        assert org_dbs.requested_org_ids == [ORG_A]

    @pytest.mark.asyncio
    async def test_aislamiento_mismo_table_name_en_otra_org_sobrevive(self, org_dbs):
        """Los registros legacy se borran por table_name: solo en la BD de la org que borra."""
        from app.services.schema_agent_service import delete_table

        tid_a = org_dbs.db(ORG_A).add_table("ventas", ["a"], rows=[{"a": 1}], legacy_records=2)
        db_b = org_dbs.db(ORG_B)
        tid_b = db_b.add_table("ventas", ["a"], rows=[{"a": 9}], legacy_records=5)

        await delete_table(ORG_A, str(tid_a))

        assert tid_b in db_b.tables
        assert db_b.rows_of(tid_b) == [{"a": 9}]
        assert len(db_b.records) == 5

    @pytest.mark.asyncio
    async def test_usa_el_pool_de_la_org_recibida(self, org_dbs):
        from app.services.schema_agent_service import delete_table

        tid = org_dbs.db(ORG_B).add_table("t", ["a"])

        await delete_table(ORG_B, str(tid))

        assert org_dbs.requested_org_ids == [ORG_B]
        assert tid not in org_dbs.db(ORG_B).tables

    # -- atomicidad / entradas invalidas -------------------------------------

    @pytest.mark.asyncio
    async def test_fallo_a_mitad_del_borrado_no_deja_estado_parcial(self, org_dbs):
        from app.services.schema_agent_service import delete_table

        db = org_dbs.db(ORG_A)
        victima, _ = _seed_two_tables(db)
        db.fail_when = lambda q, args: q.startswith("delete from data_records")

        with pytest.raises(Exception):
            await delete_table(ORG_A, str(victima))

        # todo o nada: la tabla debe conservar sus 3 filas
        assert victima in db.tables
        assert len(db.rows_of(victima)) == 3

    @pytest.mark.asyncio
    async def test_table_id_mal_formado_retorna_error(self, org_dbs):
        from app.services.schema_agent_service import delete_table

        result = await delete_table(ORG_A, "no-es-un-uuid")

        assert "error" in result

    @pytest.mark.asyncio
    async def test_router_traduce_tabla_inexistente_a_404(self, org_dbs):
        from fastapi import HTTPException
        from app.routers import schema as schema_router

        with pytest.raises(HTTPException) as exc_info:
            await schema_router.delete_table(str(uuid.uuid4()), current_user=_user(ORG_A))

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_router_usa_org_id_del_usuario_autenticado(self, org_dbs):
        """El router debe pasar current_user.org_id (del JWT), no otro valor."""
        from app.routers import schema as schema_router

        db_b = org_dbs.db(ORG_B)
        tid = db_b.add_table("t", ["a"], rows=[{"a": 1}])

        result = await schema_router.delete_table(str(tid), current_user=_user(ORG_B))

        assert result["rows_deleted"] == 1
        assert org_dbs.requested_org_ids == [ORG_B]


# ---------------------------------------------------------------------------
# delete_row (router)
# ---------------------------------------------------------------------------

class TestDeleteRow:
    @pytest.mark.asyncio
    async def test_borra_solo_la_fila_pedida_y_recalcula_conteo(self, org_dbs):
        from app.routers import schema as schema_router

        db = org_dbs.db(ORG_A)
        tid = db.add_table("t", ["a"], rows=[{"a": 1}, {"a": 2}, {"a": 3}])
        objetivo = db.row_ids_of(tid)[1]

        result = await schema_router.delete_row(str(tid), str(objetivo), current_user=_user(ORG_A))

        assert result == {"deleted": True, "new_count": 2}
        assert db.rows_of(tid) == [{"a": 1}, {"a": 3}]
        assert db.tables[tid]["row_count"] == 2

    @pytest.mark.asyncio
    async def test_fila_de_otra_tabla_no_se_borra(self, org_dbs):
        """El WHERE exige id Y table_id: una fila ajena a la tabla de la URL sobrevive."""
        from app.routers import schema as schema_router

        db = org_dbs.db(ORG_A)
        t1 = db.add_table("t1", ["a"], rows=[{"a": 1}])
        t2 = db.add_table("t2", ["a"], rows=[{"a": 2}])
        fila_de_t2 = db.row_ids_of(t2)[0]

        result = await schema_router.delete_row(str(t1), str(fila_de_t2), current_user=_user(ORG_A))

        assert db.rows_of(t2) == [{"a": 2}]
        assert db.rows_of(t1) == [{"a": 1}]
        assert result["new_count"] == 1

    @pytest.mark.asyncio
    async def test_aislamiento_otra_org_no_puede_borrar_filas_ajenas(self, org_dbs):
        from app.routers import schema as schema_router

        db_b = org_dbs.db(ORG_B)
        tid_b = db_b.add_table("t", ["a"], rows=[{"a": 1}, {"a": 2}])
        fila_b = db_b.row_ids_of(tid_b)[0]
        org_dbs.db(ORG_A)

        await schema_router.delete_row(str(tid_b), str(fila_b), current_user=_user(ORG_A))

        assert len(db_b.rows_of(tid_b)) == 2
        assert db_b.tables[tid_b]["row_count"] == 2
        assert org_dbs.requested_org_ids == [ORG_A]

    @pytest.mark.xfail(
        strict=True,
        reason="routers/schema.py:182-192 delete_row responde {'deleted': True} aunque la fila no exista "
               "(ni la tabla): el DELETE no se verifica y no hay 404",
    )
    @pytest.mark.asyncio
    async def test_fila_inexistente_no_reporta_deleted_true(self, org_dbs):
        from app.routers import schema as schema_router

        db = org_dbs.db(ORG_A)
        tid = db.add_table("t", ["a"], rows=[{"a": 1}])

        try:
            result = await schema_router.delete_row(str(tid), str(uuid.uuid4()), current_user=_user(ORG_A))
        except Exception as exc:  # un 404 tambien es una respuesta correcta
            assert getattr(exc, "status_code", None) == 404
        else:
            assert result["deleted"] is False

    @pytest.mark.asyncio
    async def test_ids_mal_formados_dan_error_http_controlado(self, org_dbs):
        from fastapi import HTTPException
        from app.routers import schema as schema_router

        tid = org_dbs.db(ORG_A).add_table("t", ["a"])

        with pytest.raises(HTTPException) as exc_info:
            await schema_router.delete_row(str(tid), "no-es-uuid", current_user=_user(ORG_A))
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Fila no encontrada"

        with pytest.raises(HTTPException) as exc_info:
            await schema_router.delete_row("no-es-uuid", str(uuid.uuid4()), current_user=_user(ORG_A))
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Tabla no encontrada"

    @pytest.mark.asyncio
    async def test_table_id_mal_formado_en_otros_endpoints_da_404(self, org_dbs):
        from fastapi import HTTPException
        from app.routers import schema as schema_router

        for endpoint in (
            schema_router.get_table_rows,
            schema_router.download_template,
            schema_router.export_table_data,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await endpoint("no-es-uuid", current_user=_user(ORG_A))
            assert exc_info.value.status_code == 404, endpoint.__name__
