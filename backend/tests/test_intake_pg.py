"""Carga inteligente contra un Postgres REAL desechable — PI0320251.

Se OMITE por defecto: necesita un Postgres local, descartable y accesible sin contrasena (trust) cuyo puerto se indica
en CHAT_TOOLS_TEST_PG_PORT (usuario en CHAT_TOOLS_TEST_PG_USER, por defecto 'tester'). Solo 127.0.0.1; crea y borra
sus propias bases. NUNCA apuntar a Neon ni a un servidor compartido. Gemini no participa (sin clave).

Cubre lo que la BD emulada no puede: jsonb real (columns_definition como texto, filas), la creacion REAL de la base de
una organizacion (create_org_database sin plantillas), el rango de fechas calculado por el motor, la deteccion de
cargas duplicadas sobre filas reales, los hallazgos de punta a punta (SQL del motor) y el aislamiento entre bases.
"""

import io
import json
import os
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from starlette.datastructures import UploadFile

from app.services import business_insights_service as svc
from app.services import intake_ontology as onto
from app.services import intake_service as intake
from app.services import schema_ai_service as ai
from tests.insights_support import FERRETERIA, NOW, item, metrics

PORT = os.environ.get("CHAT_TOOLS_TEST_PG_PORT")
pytestmark = pytest.mark.skipif(not PORT, reason="define CHAT_TOOLS_TEST_PG_PORT para usar un Postgres local desechable")

asyncpg = pytest.importorskip("asyncpg")
HOST = "127.0.0.1"  # fijo a proposito
USER = os.environ.get("CHAT_TOOLS_TEST_PG_USER", "tester")


@pytest.fixture
async def pg():
    """Una organizacion REAL (su base la crea create_org_database) en el Postgres desechable. Devuelve (org_id, admin)."""
    from app import database

    org_id = str(uuid.uuid4())
    settings = SimpleNamespace(
        DATABASE_HOST=HOST, DATABASE_PORT=int(PORT), DATABASE_USER=USER, DATABASE_PASSWORD="", DATABASE_NAME="postgres",
        DATABASE_SSL=False, GOOGLE_API_KEY="", GEMINI_MODEL="m", INTAKE_AI_ENABLED=True, INTAKE_AI_TIMEOUT_SECONDS=5.0,
        INTAKE_AI_MAX_OUTPUT_TOKENS=1200, INTAKE_THINKING_LEVEL="low", INTAKE_AI_MAX_CALLS_PER_REQUEST=8,
        INTAKE_AI_MAX_CALLS_PER_ORG_HOUR=40,
    )
    ai.clear_memory_cache()
    with patch("app.database.get_settings", return_value=settings), \
            patch("app.services.schema_ai_service.get_settings", return_value=settings):
        await database.create_org_database(org_id, None)
        try:
            yield org_id
        finally:
            await database.close_all_pools()
            admin = await asyncpg.connect(host=HOST, port=int(PORT), user=USER, database="postgres")
            await admin.execute(f'DROP DATABASE IF EXISTS "{database._org_db_name(org_id)}" WITH (FORCE)')
            await admin.close()
    ai.clear_memory_cache()


def up(name: str, text: str) -> UploadFile:
    return UploadFile(file=io.BytesIO(text.encode("utf-8")), filename=name)


async def subir(org, *pairs, strip=False):
    proposal = await intake.analyze_uploads(org, [up(n, t) for n, t in pairs])
    plan = []
    for f in proposal["files"]:
        for s in f["sheets"]:
            if s["status"] != "ready":
                continue
            d = s["destination"]
            plan.append({"file_name": f["file_name"], "sheet_name": s["sheet_name"],
                         "action": "append" if d["action"] == "append" else "create", "table_id": d["table_id"],
                         "into_sheet": d["into_sheet"], "display_name": d.get("new_display_name"), "kind": s["kind"],
                         "mapping_source": s["mapping_source"],
                         "columns": [{"name": c["name"], "role": c["role"], "confidence": c["confidence"]} for c in s["columns"]]})
    done = await intake.commit_uploads(org, [up(n, t) for n, t in pairs], plan)
    return proposal, done


def ferreteria(name: str) -> str:
    return (FERRETERIA / f"{name}.csv").read_text(encoding="utf-8")


EN_PRODUCTOS = {"nombre": "name", "categoria": "category", "precio_compra": "cost", "precio_venta": "price",
                "stock": "qty on hand", "proveedor": "supplier", "codigo": "sku"}
EN_VENTAS = {"fecha": "date", "producto": "product", "cantidad": "qty", "precio_unitario": "price", "total": "amount",
             "cliente": "customer", "metodo_pago": "payment method"}


def to_english(csv_text: str, mapping: dict) -> str:
    head, _, rest = csv_text.partition("\n")
    return ",".join(mapping[h] for h in head.split(",")) + "\n" + rest


async def test_la_organizacion_nace_sin_hojas_de_plantilla(pg):
    tables = await intake.load_org_tables(pg)
    assert tables == []


async def test_ferreteria_en_espanol_y_en_ingles_dan_exactamente_los_mismos_hallazgos(pg):
    org_en = str(uuid.uuid4())
    from app import database

    _p, done = await subir(pg, ("productos.csv", ferreteria("productos")), ("ventas.csv", ferreteria("ventas")))
    assert done["totals"]["errors"] == 0 and done["totals"]["created"] == 2
    es = await svc.get_business_insights(pg, now=NOW)
    assert [i["id"] for i in es["items"]] == ["capital_inventario", "sin_movimiento", "clientes_concentracion",
                                              "productos_estrella", "reposicion", "margen_bajo"]
    await database.create_org_database(org_en, None)
    try:
        _p, done = await subir(org_en, ("products.csv", to_english(ferreteria("productos"), EN_PRODUCTOS)),
                               ("sales.csv", to_english(ferreteria("ventas"), EN_VENTAS)))
        assert done["totals"]["errors"] == 0 and done["totals"]["created"] == 2
        en = await svc.get_business_insights(org_en, now=NOW)
        assert [i["id"] for i in en["items"]] == [i["id"] for i in es["items"]]
        for a, b in zip(es["items"], en["items"]):
            assert metrics(a) == metrics(b)
    finally:
        await database.close_all_pools()
        admin = await asyncpg.connect(host=HOST, port=int(PORT), user=USER, database="postgres")
        await admin.execute(f'DROP DATABASE IF EXISTS "{database._org_db_name(org_en)}" WITH (FORCE)')
        await admin.close()


async def test_metadata_jsonb_real_rango_de_fechas_y_roles(pg):
    _p, done = await subir(pg, ("ventas.csv", ferreteria("ventas")))
    tid = done["results"][0]["table_id"]
    tables = await intake.load_org_tables(pg)
    cols = tables[0]["columns_definition"]
    assert isinstance(cols, list) and onto.read_sheet_meta(cols)["kind"] == "ventas"
    fecha = next(c for c in cols if c["name"] == "fecha")
    assert fecha["role"] == "fecha" and fecha["type"] == "date" and len(fecha["range"]) == 2   # rango calculado por el motor
    assert fecha["range"][0] == "2025-07-02"
    assert onto.column_roles(cols)["metodo_pago"]["role"] == "metodo_pago"
    assert tid == str(tables[0]["id"])


async def test_duplicado_se_detecta_sobre_filas_reales_y_una_carga_nueva_se_suma(pg):
    csv = ferreteria("ventas")
    await subir(pg, ("ventas julio.csv", csv))
    _p, done = await subir(pg, ("ventas julio otra vez.csv", csv))
    assert done["results"][0]["status"] == "duplicate"
    lines = csv.strip().split("\n")
    nuevas = "\n".join([lines[0]] + [l.replace("2025-", "2026-") for l in lines[1:6]])
    _p, done = await subir(pg, ("ventas 2026.csv", nuevas))
    r = done["results"][0]
    assert r["status"] == "appended" and r["rows_inserted"] == 5
    tables = await intake.load_org_tables(pg)
    assert len(tables) == 1 and tables[0]["row_count"] == len(lines) - 1 + 5
    fecha = next(c for c in tables[0]["columns_definition"] if c["name"] == "fecha")
    assert fecha["range"][1].startswith("2026-")                    # el rango se extiende al sumar


async def test_inventario_y_listas_de_clientes_distintas_no_se_mezclan_en_postgres(pg):
    _p, done = await subir(pg, ("ventas.csv", ferreteria("ventas")), ("inventario.csv", ferreteria("productos")))
    assert [r["status"] for r in done["results"]] == ["created", "created"]
    a = "Nombre,Telefono,Correo\nAna,3105551234,a@x.co\n"
    b = "Cliente,Nit,Direccion,Ciudad\nFerreteria Sol,900123456,Calle 1,Cali\n"
    await subir(pg, ("clientes.csv", a))
    _p, done = await subir(pg, ("clientes empresas.csv", b))
    assert done["results"][0]["status"] == "created"
    kinds = sorted(onto.read_sheet_meta(t["columns_definition"])["kind"] for t in await intake.load_org_tables(pg))
    assert kinds == ["clientes", "clientes", "productos", "ventas"]


async def test_correccion_de_roles_sobrevive_en_la_bd_y_se_reutiliza(pg):
    await subir(pg, ("hoja.csv", "C1,C2,C3\nMartillo,1000,10\nClavos,50,200\n"))
    tid = str((await intake.load_org_tables(pg))[0]["id"])
    res = await intake.update_table_roles(pg, tid, {"c1": "producto_nombre", "c2": "costo_unitario", "c3": "stock"}, "productos")
    assert res["mapping_source"] == "user"
    ai.clear_memory_cache()                                          # otra instancia: solo queda lo guardado en la BD
    proposal = await intake.analyze_uploads(pg, [up("hoja_nueva.csv", "C1,C2,C3\nSierra,5000,2\n")])
    s = proposal["files"][0]["sheets"][0]
    assert s["kind"] == "productos" and s["mapping_source"] == "user" and s["tokens"]["model_calls"] == 0


async def test_aislamiento_entre_organizaciones(pg):
    from app import database

    otra = str(uuid.uuid4())
    await database.create_org_database(otra, None)
    try:
        await subir(pg, ("ventas.csv", ferreteria("ventas")))
        assert await intake.load_org_tables(otra) == []
        tid = str((await intake.load_org_tables(pg))[0]["id"])
        with pytest.raises(intake.IntakeError):
            await intake.update_table_roles(otra, tid, {"fecha": "fecha"}, "ventas")
        _p, done = await subir(otra, ("ventas.csv", ferreteria("ventas")))
        assert done["results"][0]["status"] == "created"            # no se suma a la hoja de la otra organizacion
    finally:
        await database.close_all_pools()
        admin = await asyncpg.connect(host=HOST, port=int(PORT), user=USER, database="postgres")
        await admin.execute(f'DROP DATABASE IF EXISTS "{database._org_db_name(otra)}" WITH (FORCE)')
        await admin.close()


async def test_deshacer_carga_en_postgres_real_restaura_conteo_y_rango_de_fechas(pg):
    csv = ferreteria("ventas")
    await subir(pg, ("ventas julio.csv", csv))
    lines = csv.strip().split("\n")
    nuevas = "\n".join([lines[0]] + [l.replace("2025-", "2026-") for l in lines[1:6]])
    _p, done = await subir(pg, ("ventas 2026.csv", nuevas))
    r = done["results"][0]
    assert r["status"] == "appended" and r["undo"]["action"] == "delete_rows"
    res = await intake.undo_commit_load(pg, r["table_id"], r["undo"]["loaded_at"])
    assert res["rows_deleted"] == 5 and res["total_rows"] == len(lines) - 1
    t = (await intake.load_org_tables(pg))[0]
    assert t["row_count"] == len(lines) - 1
    fecha = next(c for c in t["columns_definition"] if c["name"] == "fecha")
    assert fecha["range"][1].startswith("2025-")                    # el rango vuelve a lo de antes
    from app.services import schema_agent_service as sa
    pool = await sa.get_org_pool(pg)
    async with pool.acquire() as conn:
        legacy = await conn.fetchval("SELECT count(*) FROM data_records")
    assert legacy == len(lines) - 1                                 # las filas legacy de la carga deshecha tambien salieron
