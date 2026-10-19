"""Hallazgos que usan los roles GUARDADOS por la carga inteligente — PI0320251.

Flujo real sobre la BD emulada y el motor reemplazado por el oraculo pandas: se sube con intake (analyze/commit) o se
corrige un rol, y GET /insights calcula sobre lo guardado. Cubre encabezados en ingles, genericos ("C1"), cruce por
codigo en vez de nombre, tipo confirmado que el detector por sinonimos no puede pisar, mensajes de lo que falta y
el respaldo por sinonimos para tablas sin metadata.
"""

import io
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from starlette.datastructures import UploadFile

from app.services import business_insights_service as svc
from app.services import intake_ontology as onto
from app.services import intake_service as intake
from app.services import schema_ai_service as ai
from tests.fake_org_db import FakeOrgDBs
from tests.insights_support import NOW, ORG_A, item, metrics, missing
from tests.query_oracle import fake_run_plans

PRODUCTOS_ES = "Nombre,Costo,Existencias\nMartillo,1000,10\nClavos,50,200\nSierra,5000,2\n"
VENTAS_ES = ("Fecha,Producto,Cantidad,Precio Unitario,Cliente\n"
             "2025-07-02,Martillo,2,1500,Ana\n2025-08-10,Clavos,100,80,Ana\n2025-10-08,Martillo,1,1500,Luis\n")
PRODUCTOS_EN = "name,cost,stock\nMartillo,1000,10\nClavos,50,200\nSierra,5000,2\n"
VENTAS_EN = ("date,product,qty,price,customer\n"
             "2025-07-02,Martillo,2,1500,Ana\n2025-08-10,Clavos,100,80,Ana\n2025-10-08,Martillo,1,1500,Luis\n")


@pytest.fixture
def env():
    ai.clear_memory_cache()
    dbs = FakeOrgDBs()
    settings = SimpleNamespace(GOOGLE_API_KEY="", GEMINI_MODEL="m", INTAKE_AI_ENABLED=True, INTAKE_AI_TIMEOUT_SECONDS=5.0,
                               INTAKE_AI_MAX_OUTPUT_TOKENS=1200, INTAKE_THINKING_LEVEL="low",
                               INTAKE_AI_MAX_CALLS_PER_REQUEST=8, INTAKE_AI_MAX_CALLS_PER_ORG_HOUR=40)
    with patch("app.services.schema_agent_service.get_org_pool", dbs.get_org_pool), \
            patch("app.services.business_insights_service.get_org_pool", dbs.get_org_pool), \
            patch("app.services.data_query_engine.run_plans", fake_run_plans()), \
            patch("app.services.schema_ai_service.get_settings", return_value=settings):
        yield dbs
    ai.clear_memory_cache()


def up(name, text):
    return UploadFile(file=io.BytesIO(text.encode("utf-8")), filename=name)


async def subir(*pairs):
    proposal = await intake.analyze_uploads(ORG_A, [up(n, t) for n, t in pairs])
    plan = []
    for f in proposal["files"]:
        for s in f["sheets"]:
            d = s["destination"]
            plan.append({"file_name": f["file_name"], "sheet_name": s["sheet_name"],
                         "action": "append" if d["action"] == "append" else "create", "table_id": d["table_id"],
                         "into_sheet": d["into_sheet"], "display_name": d.get("new_display_name"), "kind": s["kind"],
                         "mapping_source": s["mapping_source"],
                         "columns": [{"name": c["name"], "role": c["role"], "confidence": c["confidence"]} for c in s["columns"]]})
    done = await intake.commit_uploads(ORG_A, [up(n, t) for n, t in pairs], plan)
    assert done["totals"]["errors"] == 0, done
    return proposal, done


async def hallazgos():
    return await svc.get_business_insights(ORG_A, now=NOW)


class TestEncabezadosAjenos:
    async def test_encabezados_en_ingles_dan_los_mismos_numeros_que_en_espanol(self, env):
        await subir(("productos.csv", PRODUCTOS_ES), ("ventas.csv", VENTAS_ES))
        es = await hallazgos()
        env.db(ORG_A).tables.clear()
        env.db(ORG_A).rows.clear()
        await subir(("products.csv", PRODUCTOS_EN), ("sales.csv", VENTAS_EN))
        en = await hallazgos()
        assert [i["id"] for i in en["items"]] == [i["id"] for i in es["items"]] and en["items"]
        for a, b in zip(es["items"], en["items"]):
            assert metrics(a) == metrics(b) and a["sentence"] == b["sentence"]
        # numeros a mano: mercancia = 10x1000 + 200x50 + 2x5000 = 30.000
        assert metrics(item(en, "capital_inventario"))["Mercancía a costo"] == 30000

    async def test_columnas_genericas_corregidas_por_el_duenio_habilitan_los_hallazgos(self, env):
        await subir(("hoja1.csv", "C1,C2,C3\nMartillo,1000,10\nClavos,50,200\nSierra,5000,2\n"),
                    ("hoja2.csv", "D1,D2,D3,D4,D5\n2025-07-02,Martillo,2,1500,Ana\n2025-08-10,Clavos,100,80,Ana\n2025-10-08,Martillo,1,1500,Luis\n"))
        antes = await hallazgos()
        assert antes["items"] == []                              # sin tipo, no hay nada que calcular
        tablas = {t["table_name"]: t for t in env.db(ORG_A).tables.values()}
        await intake.update_table_roles(ORG_A, str(tablas["hoja1"]["id"]),
                                        {"c1": "producto_nombre", "c2": "costo_unitario", "c3": "stock"}, "productos")
        await intake.update_table_roles(ORG_A, str(tablas["hoja2"]["id"]),
                                        {"d1": "fecha", "d2": "producto", "d3": "cantidad", "d4": "precio_unitario", "d5": "cliente"}, "ventas")
        despues = await hallazgos()
        assert metrics(item(despues, "capital_inventario"))["Mercancía a costo"] == 30000

    async def test_cruce_por_codigo_cuando_las_ventas_traen_el_codigo_no_el_nombre(self, env):
        prod = "Nombre,Codigo,Costo,Existencias\nMartillo,HM-001,1000,10\nClavos,CL-002,50,200\nSierra,SI-003,5000,2\n"
        ven = ("Fecha,Producto,Cantidad,Precio Unitario,Cliente\n"
               "2025-07-02,HM-001,2,1500,Ana\n2025-08-10,CL-002,100,80,Ana\n2025-10-08,HM-001,1,1500,Luis\n")
        await subir(("productos.csv", prod), ("ventas.csv", ven))
        r = await hallazgos()
        # sin cruce por codigo: 3 ventas "no estan en tu hoja de productos"; con el cruce, utilidad: martillo 3x500 + clavos 100x30
        assert not any("no están en tu hoja de productos" in n for it in r["items"] for n in it["how"]["notes"])
        assert metrics(item(r, "productos_estrella"))["Utilidad total"] == 1500 + 3000

    async def test_ventas_a_las_que_les_falta_cantidad_dicen_que_falta_en_palabras_simples(self, env):
        await subir(("productos.csv", PRODUCTOS_ES),
                    ("ventas.csv", "Fecha,Producto,Total\n2025-07-02,Martillo,3000\n2025-08-10,Clavos,8000\n"))
        r = await hallazgos()
        assert r["items"] == []
        assert missing(r, "capital_inventario")["needs"].startswith("A tu hoja de ventas ('Ventas') le falta: cantidad.")


class TestTipoConfirmado:
    async def _tabla(self, env, nombre, cols, roles, kind, source="user", conf=1.0, rows=None):
        meta = onto.make_sheet_meta(kind, conf, source, None)
        defs = onto.with_sheet_meta(
            [{"name": c, "type": "number" if c in ("cantidad", "total", "precio_unitario", "costo", "stock") else "text",
              "role": roles.get(c, "otro"), "role_confidence": 1.0} for c in cols], meta)
        tid = env.db(ORG_A).add_table(nombre, cols, rows or [], display_name=nombre.title())
        env.db(ORG_A).tables[tid]["columns_definition"] = __import__("json").dumps(defs)
        return tid

    async def test_una_hoja_de_compras_no_se_toma_por_ventas_aunque_los_sinonimos_lo_crean(self, env):
        cols = ["fecha", "producto", "cantidad", "precio_unitario", "total"]
        await self._tabla(env, "compras_octubre", cols, {c: c for c in ["fecha", "producto", "cantidad", "total"]} | {"precio_unitario": "costo_unitario"},
                          "compras", rows=[{"fecha": "2025-10-01", "producto": "Martillo", "cantidad": 5, "precio_unitario": 900, "total": 4500}])
        await self._tabla(env, "lista", ["nombre", "costo", "stock"],
                          {"nombre": "producto_nombre", "costo": "costo_unitario", "stock": "stock"}, "productos",
                          rows=[{"nombre": "Martillo", "costo": 1000, "stock": 10}])
        r = await hallazgos()
        assert r["items"] == []
        assert "Necesito una hoja de ventas" in missing(r, "capital_inventario")["needs"]

    async def test_misma_hoja_sin_metadata_si_entra_por_sinonimos_respaldo(self, env):
        env.db(ORG_A).add_table("compras_octubre", ["fecha", "producto", "cantidad", "precio_unitario", "total"],
                                [{"fecha": "2025-10-01", "producto": "Martillo", "cantidad": 5, "precio_unitario": 900, "total": 4500}],
                                column_types={"fecha": "date", "cantidad": "integer", "precio_unitario": "number", "total": "number"})
        env.db(ORG_A).add_table("productos", ["nombre", "costo", "stock"], [{"nombre": "Martillo", "costo": 1000, "stock": 10}],
                                column_types={"costo": "number", "stock": "integer"})
        r = await hallazgos()
        assert item(r, "capital_inventario")          # el respaldo clasifica la hoja vieja como ventas

    async def test_tipo_heuristico_dudoso_no_bloquea_el_respaldo(self, env):
        cols = ["fecha", "producto", "cantidad", "precio_unitario", "total"]
        tid = await self._tabla(env, "ventas", cols, {}, "otro", source="heuristic", conf=0.3,
                                rows=[{"fecha": "2025-10-01", "producto": "Martillo", "cantidad": 5, "precio_unitario": 900, "total": 4500}])
        env.db(ORG_A).add_table("productos", ["nombre", "costo", "stock"], [{"nombre": "Martillo", "costo": 1000, "stock": 10}],
                                column_types={"costo": "number", "stock": "integer"})
        r = await hallazgos()
        assert item(r, "capital_inventario")

    async def test_hoja_de_ventas_incompleta_se_explica(self, env):
        cols = ["fecha", "producto", "total"]
        await self._tabla(env, "ventas_mayo", cols, {"fecha": "fecha", "producto": "producto", "total": "total"}, "ventas",
                          rows=[{"fecha": "2025-10-01", "producto": "Martillo", "total": 4500}])
        await self._tabla(env, "lista", ["nombre", "costo", "stock"],
                          {"nombre": "producto_nombre", "costo": "costo_unitario", "stock": "stock"}, "productos",
                          rows=[{"nombre": "Martillo", "costo": 1000, "stock": 10}])
        r = await hallazgos()
        needs = missing(r, "capital_inventario")["needs"]
        assert needs.startswith("A tu hoja de ventas ('Ventas_Mayo') le falta: cantidad.")
        assert "corrígela en Mis datos" in needs

    async def test_hoja_de_cuentas_por_cobrar_confirmada_quita_el_aviso_de_cartera(self, env):
        await self._tabla(env, "deudores", ["cliente", "saldo", "vence"],
                          {"cliente": "cliente", "saldo": "valor", "vence": "fecha_vencimiento"}, "cuentas_por_cobrar",
                          rows=[{"cliente": "Ana", "saldo": 100, "vence": "2025-11-01"}])
        r = await hallazgos()
        assert all(m["id"] != "cartera" for m in r["missing"])
        sin = await svc.get_business_insights(ORG_A, now=NOW)
        assert sin is not None

    async def test_ventas_de_otra_sede_con_una_columna_mas_se_suman_y_la_columna_nueva_se_conserva(self, env):
        await subir(("productos.csv", PRODUCTOS_ES), ("ventas.csv", VENTAS_ES))
        otra = ("Fecha,Producto,Cantidad,Precio Unitario,Cliente,Sede\n"
                "2025-09-01,Martillo,1,1500,Ana,Norte\n2025-09-02,Clavos,5,80,Eva,Norte\n")
        _, done = await subir(("ventas norte.csv", otra))
        assert done["results"][0]["status"] == "appended"
        ventas = next(t for t in env.db(ORG_A).tables.values() if t["table_name"] == "ventas")
        assert ventas["row_count"] == 5
        assert "sede" in [c["name"] for c in onto.parse_columns(ventas["columns_definition"])]
        r = await hallazgos()
        assert metrics(item(r, "capital_inventario"))["Mercancía a costo"] == 30000
