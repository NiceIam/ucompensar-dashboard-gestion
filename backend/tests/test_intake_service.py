"""Carga inteligente (intake_service): analizar, proponer, confirmar y guardar — PI0320251.

BD de la organizacion emulada (tests/fake_org_db.py) y Gemini SIMULADO. Valores a mano. Cubre el emparejamiento
seguro (inventario dentro de ventas, dos listas de clientes distintas NO se mezclan), Excel de varias hojas,
encabezados en ingles/genericos, cache (0 llamadas), duplicados, validacion estricta y aislamiento por organizacion.
"""

import io
import json
import warnings
from types import SimpleNamespace
from unittest.mock import patch

import openpyxl
import pytest
from starlette.datastructures import UploadFile

from app.services import intake_ontology as onto
from app.services import intake_service as intake
from app.services import schema_ai_service as ai
from tests.fake_gemini_models import ai_answer, make_fake_genai_models
from tests.fake_org_db import FakeOrgDBs

ORG_A = "550e8400-e29b-41d4-a716-446655440000"
ORG_B = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"

VENTAS_CSV = (
    "Fecha,Producto,Cantidad,Precio Unitario,Total,Cliente\n"
    "2026-05-02,Gasas,3,1500,4500,Ana\n"
    "2026-07-15,Jeringas,2,800,1600,Luis\n"
    "2026-10-17,Gasas,1,1500,1500,Ana\n"
)
INVENTARIO_CSV = (
    "Producto,Cantidad,Costo,Precio Venta\n"
    "Gasas,10,900,1500\n"
    "Jeringas,20,500,800\n"
)
CLIENTES_A = "Nombre,Telefono,Correo\nAna,3105551234,ana@x.co\nLuis,3115559876,luis@x.co\n"
CLIENTES_B = "Cliente,Nit,Direccion,Ciudad\nFerreteria Sol,900123456,Calle 1,Cali\nBodega Luna,800765432,Calle 2,Bogota\n"


@pytest.fixture(autouse=True)
def _env():
    """Sin clave por defecto: ningun test toca la red; los que usan el modelo lo parchean explicitamente."""
    ai.clear_memory_cache()
    settings = SimpleNamespace(GOOGLE_API_KEY="", GEMINI_MODEL="m", INTAKE_AI_ENABLED=True, INTAKE_AI_TIMEOUT_SECONDS=5.0,
                               INTAKE_AI_MAX_OUTPUT_TOKENS=1200, INTAKE_THINKING_LEVEL="low",
                               INTAKE_AI_MAX_CALLS_PER_REQUEST=8, INTAKE_AI_MAX_CALLS_PER_ORG_HOUR=40)
    with patch("app.services.schema_ai_service.get_settings", return_value=settings), \
            warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yield settings
    ai.clear_memory_cache()


@pytest.fixture
def dbs():
    d = FakeOrgDBs()
    with patch("app.services.schema_agent_service.get_org_pool", d.get_org_pool):
        yield d


def csv_up(name: str, text: str) -> UploadFile:
    return UploadFile(file=io.BytesIO(text.encode("utf-8")), filename=name)


def xlsx_up(name: str, sheets: dict[str, list[list]]) -> UploadFile:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for sname, rows in sheets.items():
        ws = wb.create_sheet(title=sname)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return UploadFile(file=io.BytesIO(buf.getvalue()), filename=name)


def sheets_of(result, file_index=0):
    return result["files"][file_index]["sheets"]


def plan_from(proposal: dict, **over) -> list[dict]:
    """El plan que mandaria el frontend tal cual la propuesta (sin cambios del usuario)."""
    items = []
    for f in proposal["files"]:
        for s in f["sheets"]:
            if s["status"] != "ready":
                continue
            d = s["destination"]
            item = {
                "file_name": f["file_name"], "sheet_name": s["sheet_name"],
                "action": "create" if d["action"] in ("create", "ask") else "append",
                "table_id": d["table_id"], "into_sheet": d["into_sheet"], "display_name": d.get("new_display_name"),
                "kind": s["kind"], "mapping_source": s["mapping_source"],
                "columns": [{"name": c["name"], "role": c["role"], "confidence": c["confidence"]} for c in s["columns"]],
            }
            if d["action"] == "append":
                item["display_name"] = None
            item.update(over)
            items.append(item)
    return items


async def analyze_and_commit(org, files_factory):
    proposal = await intake.analyze_uploads(org, files_factory())
    done = await intake.commit_uploads(org, files_factory(), plan_from(proposal))
    return proposal, done


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------

class TestAnalyze:
    async def test_ventas_clara_propone_hoja_nueva_con_frase_para_el_duenio(self, dbs):
        r = await intake.analyze_uploads(ORG_A, [csv_up("ventas octubre.csv", VENTAS_CSV)])
        s = sheets_of(r)[0]
        assert s["status"] == "ready" and s["kind"] == "ventas" and s["kind_label"] == "ventas"
        assert s["rows"] == 3 and s["columns_count"] == 6 and s["needs_review"] is False
        assert s["summary"] == "Encontré tus ventas: 3 filas, de mayo a octubre de 2026."
        assert s["period"] == {"from": "2026-05-02", "to": "2026-10-17"}
        assert s["destination"]["action"] == "create" and s["destination"]["new_display_name"] == "Ventas octubre"
        assert s["mapping_source"] == "heuristic" and s["tokens"]["model_calls"] == 0
        total = next(c for c in s["columns"] if c["role"] == "total")
        assert total["original_name"] == "Total" and total["explain"] == "lo que sumó toda la venta"
        assert total["role_label"] == "Total de la venta" and total["confidence"] >= 0.9
        assert r["ai"]["model_calls"] == 0
        assert dbs.db(ORG_A).tables == {}                       # analyze NO guarda nada

    async def test_columna_con_abreviatura_se_explica_en_palabras_del_duenio(self, dbs):
        csv = "Nombre,Vlr Compra,Existencias,Precio Venta\nGasas,900,10,1500\n"
        s = sheets_of(await intake.analyze_uploads(ORG_A, [csv_up("lista.csv", csv)]))[0]
        col = next(c for c in s["columns"] if c["original_name"] == "Vlr Compra")
        assert col["role"] == "costo_unitario" and col["explain"] == "lo que pagaste por cada producto"

    async def test_excel_de_varias_hojas_una_propuesta_por_hoja(self, dbs):
        up = xlsx_up("negocio.xlsx", {
            "Ventas": [["Fecha", "Producto", "Cantidad", "Total"], ["2026-05-02", "Gasas", 3, 4500]],
            "Productos": [["Nombre", "Costo", "Stock"], ["Gasas", 900, 10]],
            "Clientes": [["Nombre", "Telefono", "Email"], ["Ana", "3105551234", "a@x.co"]],
        })
        r = await intake.analyze_uploads(ORG_A, [up])
        kinds = {s["sheet_name"]: s["kind"] for s in sheets_of(r)}
        assert kinds == {"Ventas": "ventas", "Productos": "productos", "Clientes": "clientes"}
        names = {s["sheet_name"]: s["destination"]["new_display_name"] for s in sheets_of(r)}
        assert names == {"Ventas": "Ventas", "Productos": "Productos", "Clientes": "Clientes"}
        assert len({s["destination"]["new_table_name"] for s in sheets_of(r)}) == 3

    async def test_inventario_y_ventas_en_desorden_no_se_mezclan(self, dbs):
        r = await intake.analyze_uploads(ORG_A, [csv_up("inventario.csv", INVENTARIO_CSV), csv_up("ventas.csv", VENTAS_CSV)])
        inv, ven = sheets_of(r, 0)[0], sheets_of(r, 1)[0]
        assert inv["kind"] == "productos" and ven["kind"] == "ventas"
        assert inv["destination"]["action"] == "create" and ven["destination"]["action"] == "create"
        assert ven["destination"]["into_sheet"] is None

    async def test_encabezados_en_ingles(self, dbs):
        csv = "date,product,qty,price,customer\n2026-05-02,Gasas,3,1500,Ana\n"
        s = sheets_of(await intake.analyze_uploads(ORG_A, [csv_up("sales.csv", csv)]))[0]
        assert s["kind"] == "ventas"
        assert [c["role"] for c in s["columns"]] == ["fecha", "producto", "cantidad", "precio_unitario", "cliente"]

    async def test_excel_con_titulo_encima_del_encabezado(self, dbs):
        up = xlsx_up("reporte.xlsx", {"Hoja1": [["REPORTE OCTUBRE"], [], ["Fecha", "Producto", "Cantidad", "Total"],
                                                ["2026-10-02", "Gasas", 3, 4500]]})
        s = sheets_of(await intake.analyze_uploads(ORG_A, [up]))[0]
        assert s["kind"] == "ventas" and s["rows"] == 1

    async def test_nombre_generico_de_archivo_usa_el_tipo(self, dbs):
        s = sheets_of(await intake.analyze_uploads(ORG_A, [csv_up("datos.csv", VENTAS_CSV)]))[0]
        assert s["destination"]["new_display_name"] == "Ventas"
        s = sheets_of(await intake.analyze_uploads(ORG_A, [csv_up("Export_2026-10-19 (1).csv", VENTAS_CSV)]))[0]
        assert s["destination"]["new_display_name"] != "Datos importados"

    async def test_hoja_vacia_archivo_ilegible_y_tipo_no_soportado(self, dbs):
        up_empty = xlsx_up("a.xlsx", {"Vacia": [], "Datos": [["a", "b"], [1, 2]]})
        bad = UploadFile(file=io.BytesIO(b"no soy un excel"), filename="roto.xlsx")
        pdf = UploadFile(file=io.BytesIO(b"%PDF"), filename="x.pdf")
        r = await intake.analyze_uploads(ORG_A, [up_empty, bad, pdf])
        assert [s["status"] for s in sheets_of(r, 0)] == ["empty", "ready"]
        assert r["files"][1]["status"] == "error" and r["files"][1]["error"]["code"] == "unreadable"
        assert r["files"][2]["error"]["code"] == "unsupported_type"
        assert "Traceback" not in json.dumps(r)

    async def test_demasiadas_filas_error_humano_por_hoja(self, dbs):
        with patch.object(intake, "MAX_ROWS", 2):
            r = await intake.analyze_uploads(ORG_A, [csv_up("v.csv", VENTAS_CSV)])
        s = sheets_of(r)[0]
        assert s["status"] == "error" and s["error"]["code"] == "too_many_rows" and "Divídela" in s["error"]["message"]

    async def test_limites_de_archivos(self, dbs):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as e:
            await intake.analyze_uploads(ORG_A, [])
        assert e.value.status_code == 422
        many = [csv_up(f"f{i}.csv", "a,b\n1,2\n") for i in range(intake.MAX_FILES + 1)]
        with pytest.raises(HTTPException) as e:
            await intake.analyze_uploads(ORG_A, many)
        assert "hasta 10" in e.value.detail

    async def test_json_se_entiende_igual(self, dbs):
        data = [{"fecha": "2026-05-02", "producto": "Gasas", "cantidad": 3, "total": 4500}]
        up = UploadFile(file=io.BytesIO(json.dumps(data).encode()), filename="ventas.json")
        s = sheets_of(await intake.analyze_uploads(ORG_A, [up]))[0]
        assert s["kind"] == "ventas"


class TestEmparejamientoSeguro:
    async def test_misma_estructura_se_suma_a_la_hoja_existente(self, dbs):
        await analyze_and_commit(ORG_A, lambda: [csv_up("ventas mayo.csv", VENTAS_CSV)])
        nuevo = VENTAS_CSV.replace("2026-05-02", "2026-11-02").replace("2026-07-15", "2026-11-05").replace("2026-10-17", "2026-11-09")
        r = await intake.analyze_uploads(ORG_A, [csv_up("ventas noviembre.csv", nuevo)])
        d = sheets_of(r)[0]["destination"]
        assert d["action"] == "append" and d["similarity"] == 1.0 and d["table_id"]
        assert "Se sumará a" in d["text"]

    async def test_dos_listas_de_clientes_distintas_no_se_mezclan(self, dbs):
        await analyze_and_commit(ORG_A, lambda: [csv_up("clientes.csv", CLIENTES_A)])
        r = await intake.analyze_uploads(ORG_A, [csv_up("clientes_empresas.csv", CLIENTES_B)])
        s = sheets_of(r)[0]
        assert s["destination"]["action"] == "create"
        _, done = await analyze_and_commit(ORG_A, lambda: [csv_up("clientes_empresas.csv", CLIENTES_B)])
        assert done["totals"]["created"] == 1 and len(dbs.db(ORG_A).tables) == 2

    async def test_misma_clase_pero_poco_parecida_se_guarda_aparte(self, dbs):
        await analyze_and_commit(ORG_A, lambda: [csv_up("ventas.csv", VENTAS_CSV)])
        otra = "Fecha,Producto,Cantidad,Total,Mesero,Mesa,Propina,Turno\n2026-05-02,Pizza,2,40000,Ana,3,2000,noche\n"
        d = sheets_of(await intake.analyze_uploads(ORG_A, [csv_up("pedidos.csv", otra)]))[0]["destination"]
        assert d["action"] == "create"

    async def test_similitud_media_se_le_pregunta_al_duenio_sin_mezclar(self, dbs):
        await analyze_and_commit(ORG_A, lambda: [csv_up("ventas.csv", VENTAS_CSV)])
        media = "Fecha,Producto,Cantidad,Total,Sede\n2026-11-02,Gasas,3,4500,Norte\n"
        s = sheets_of(await intake.analyze_uploads(ORG_A, [csv_up("ventas norte.csv", media)]))[0]
        d = s["destination"]
        assert d["action"] == "ask" and 0.5 <= d["similarity"] < 0.8 and s["needs_review"] is True
        assert d["table_id"] and d["new_display_name"] and "¿la sumo ahí o la guardo aparte?" in d["text"]
        # por omision el plan crea una hoja NUEVA: nada se mezcla en silencio
        _, done = await analyze_and_commit(ORG_A, lambda: [csv_up("ventas norte.csv", media)])
        assert done["totals"]["created"] == 1 and len(dbs.db(ORG_A).tables) == 2

    async def test_plantilla_vacia_compatible_se_llena(self, dbs):
        tid = dbs.db(ORG_A).add_table("ventas", ["fecha", "producto", "cantidad", "precio_unitario", "total", "cliente",
                                                  "metodo_pago"], [], display_name="Ventas")
        csv = "Fecha,Producto,Cantidad,Total\n2026-05-02,Gasas,3,4500\n"
        s = sheets_of(await intake.analyze_uploads(ORG_A, [csv_up("v.csv", csv)]))[0]
        assert s["destination"]["action"] == "append" and s["destination"]["table_id"] == str(tid)

    async def test_meses_del_mismo_cargue_se_juntan_en_una_sola_hoja(self, dbs):
        files = lambda: [csv_up("ventas enero.csv", VENTAS_CSV), csv_up("ventas febrero.csv", VENTAS_CSV.replace("Ana", "Eva"))]
        r = await intake.analyze_uploads(ORG_A, files())
        a, b = sheets_of(r, 0)[0], sheets_of(r, 1)[0]
        assert a["destination"]["action"] == "create" and b["destination"]["action"] == "append"
        assert b["destination"]["into_sheet"] == a["key"] and a["destination"]["new_display_name"] == "Ventas"

    async def test_kind_distinto_nunca_se_suma_aunque_compartan_columnas(self, dbs):
        await analyze_and_commit(ORG_A, lambda: [csv_up("ventas.csv", VENTAS_CSV)])
        r = await intake.analyze_uploads(ORG_A, [csv_up("inventario.csv", INVENTARIO_CSV)])
        assert sheets_of(r)[0]["destination"]["action"] == "create"

    async def test_datos_sin_tipo_solo_se_suman_con_exactamente_las_mismas_columnas(self, dbs):
        base = "Nombre,Cargo,Salario\nAna,Cajera,1500000\n"
        await analyze_and_commit(ORG_A, lambda: [csv_up("empleados.csv", base)])
        igual = sheets_of(await intake.analyze_uploads(ORG_A, [csv_up("empleados2.csv", base.replace("Ana", "Eva"))]))[0]
        distinta = sheets_of(await intake.analyze_uploads(ORG_A, [csv_up("e3.csv", "Nombre,Cargo,Salario,Eps\nAna,Cajera,1,Sura\n")]))[0]
        assert igual["destination"]["action"] == "append" and distinta["destination"]["action"] == "create"


class TestAgenteConModelo:
    GENERICA = "C1,C2,C3,C4\n2026-05-02,Gasas,3,1500\n2026-05-03,Jeringas,2,800\n"

    def _with_key(self, env):
        env.GOOGLE_API_KEY = "AIzaSyFAKEKEYFAKEKEYFAKEKEYFAKEKEY12345"

    async def test_encabezados_genericos_los_resuelve_el_modelo_una_sola_vez(self, dbs, _env):
        self._with_key(_env)
        fake = make_fake_genai_models(ai_answer("ventas", 0.9, {0: ("fecha", 0.9), 1: ("producto", 0.9),
                                                                 2: ("cantidad", 0.85), 3: ("precio_unitario", 0.8)}))
        with patch("google.genai.Client", return_value=fake.client):
            r = await intake.analyze_uploads(ORG_A, [csv_up("hoja.csv", self.GENERICA)])
            s = sheets_of(r)[0]
            assert s["kind"] == "ventas" and s["mapping_source"] == "ai" and fake.generate.await_count == 1
            assert s["tokens"]["prompt"] == 700 and r["ai"]["model_calls"] == 1
            # 2.º analisis de la MISMA estructura: 0 llamadas
            r2 = await intake.analyze_uploads(ORG_A, [csv_up("otra.csv", self.GENERICA.replace("Gasas", "Tela"))])
            assert fake.generate.await_count == 1 and sheets_of(r2)[0]["from_cache"] is True
            assert r2["ai"]["cache_hits"] == 1 and sheets_of(r2)[0]["tokens"]["model_calls"] == 0

    async def test_sin_modelo_la_hoja_generica_se_guarda_tal_cual(self, dbs):
        r = await intake.analyze_uploads(ORG_A, [csv_up("hoja.csv", self.GENERICA)])
        s = sheets_of(r)[0]
        assert s["kind"] == "otro" and s["mapping_source"] == "heuristic" and s["needs_review"] is False
        assert s["summary"].startswith("Guardaré tus datos tal cual")

    async def test_hojas_claras_no_cuestan_tokens_aunque_haya_clave(self, dbs, _env):
        self._with_key(_env)
        fake = make_fake_genai_models(ai_answer("ventas", 0.9, {}))
        with patch("google.genai.Client", return_value=fake.client) as ctor:
            r = await intake.analyze_uploads(ORG_A, [csv_up("ventas.csv", VENTAS_CSV), csv_up("inv.csv", INVENTARIO_CSV)])
        ctor.assert_not_called()
        assert r["ai"] == {"model_calls": 0, "prompt_tokens": 0, "output_tokens": 0, "thoughts_tokens": 0, "cache_hits": 0}

    async def test_baja_confianza_pide_revision(self, dbs, _env):
        self._with_key(_env)
        fake = make_fake_genai_models(ai_answer("ventas", 0.6, {0: ("fecha", 0.6), 1: ("producto", 0.6)}))
        with patch("google.genai.Client", return_value=fake.client):
            s = sheets_of(await intake.analyze_uploads(ORG_A, [csv_up("hoja.csv", self.GENERICA)]))[0]
        assert s["needs_review"] is True and s["review_reasons"]


# ---------------------------------------------------------------------------
# commit
# ---------------------------------------------------------------------------

class TestCommit:
    async def test_crea_la_hoja_con_roles_y_metadata_y_carga_las_filas(self, dbs):
        _, done = await analyze_and_commit(ORG_A, lambda: [csv_up("ventas octubre.csv", VENTAS_CSV)])
        res = done["results"][0]
        assert res["status"] == "created" and res["rows_inserted"] == 3 and res["total_rows"] == 3
        assert res["display_name"] == "Ventas octubre" and res["table_name"] == "ventas_octubre"
        assert res["undo"] == {"action": "delete_table", "table_id": res["table_id"]}
        db = dbs.db(ORG_A)
        tid = next(iter(db.tables))
        cols = db.columns_of(tid)
        meta = onto.read_sheet_meta(cols)
        assert meta["kind"] == "ventas" and meta["mapping_source"] == "heuristic" and meta["signature"]
        assert onto.column_roles(cols)["total"]["role"] == "total"
        assert [c["label"] for c in cols][:3] == ["Fecha", "Producto", "Cantidad"]
        assert next(c for c in cols if c["name"] == "fecha")["type"] == "date"
        assert len(db.rows_of(tid)) == 3 and db.tables[tid]["row_count"] == 3

    async def test_suma_a_la_existente_y_conserva_roles(self, dbs):
        await analyze_and_commit(ORG_A, lambda: [csv_up("ventas mayo.csv", VENTAS_CSV)])
        nuevo = VENTAS_CSV.replace("Ana", "Eva")
        _, done = await analyze_and_commit(ORG_A, lambda: [csv_up("ventas nov.csv", nuevo)])
        assert done["results"][0]["status"] == "appended" and done["results"][0]["total_rows"] == 6
        assert len(dbs.db(ORG_A).tables) == 1

    async def test_misma_carga_dos_veces_no_duplica(self, dbs):
        await analyze_and_commit(ORG_A, lambda: [csv_up("ventas.csv", VENTAS_CSV)])
        _, done = await analyze_and_commit(ORG_A, lambda: [csv_up("ventas.csv", VENTAS_CSV)])
        r = done["results"][0]
        assert r["status"] == "duplicate" and r["rows_inserted"] == 0 and "ya estaban" in r["message"]
        tid = next(iter(dbs.db(ORG_A).tables))
        assert len(dbs.db(ORG_A).rows_of(tid)) == 3

    async def test_meses_juntos_en_un_solo_cargue_quedan_en_una_tabla(self, dbs):
        files = lambda: [csv_up("ventas enero.csv", VENTAS_CSV), csv_up("ventas febrero.csv", VENTAS_CSV.replace("Ana", "Eva"))]
        _, done = await analyze_and_commit(ORG_A, files)
        assert [r["status"] for r in done["results"]] == ["created", "appended"]
        db = dbs.db(ORG_A)
        assert len(db.tables) == 1
        t = next(iter(db.tables.values()))
        assert t["display_name"] == "Ventas" and t["row_count"] == 6

    async def test_excel_de_varias_hojas_cada_una_en_su_tabla(self, dbs):
        make = lambda: [xlsx_up("negocio.xlsx", {
            "Ventas": [["Fecha", "Producto", "Cantidad", "Total"], ["2026-05-02", "Gasas", 3, 4500]],
            "Productos": [["Nombre", "Costo", "Stock"], ["Gasas", 900, 10]]})]
        _, done = await analyze_and_commit(ORG_A, make)
        assert done["totals"] == {"created": 2, "appended": 0, "duplicates": 0, "errors": 0, "rows_inserted": 2}
        kinds = sorted(onto.read_sheet_meta(t["columns_definition"])["kind"] for t in dbs.db(ORG_A).tables.values())
        assert kinds == ["productos", "ventas"]

    async def test_hoja_con_el_rol_corregido_por_el_duenio_se_guarda_como_user(self, dbs):
        proposal = await intake.analyze_uploads(ORG_A, [csv_up("hoja.csv", TestAgenteConModelo.GENERICA)])
        plan = plan_from(proposal)
        plan[0]["kind"] = "ventas"
        plan[0]["columns"] = [{"name": "c1", "role": "fecha", "edited": True}, {"name": "c2", "role": "producto", "edited": True},
                              {"name": "c3", "role": "cantidad", "edited": True}, {"name": "c4", "role": "total", "edited": True}]
        done = await intake.commit_uploads(ORG_A, [csv_up("hoja.csv", TestAgenteConModelo.GENERICA)], plan)
        assert done["results"][0]["status"] == "created"
        cols = dbs.db(ORG_A).columns_of(next(iter(dbs.db(ORG_A).tables)))
        assert onto.read_sheet_meta(cols)["mapping_source"] == "user"
        assert onto.column_roles(cols)["c4"] == {"role": "total", "confidence": 1.0, "label": "C4"}

    async def test_agrega_a_una_tabla_anterior_a_la_carga_inteligente_y_la_etiqueta(self, dbs):
        db = dbs.db(ORG_A)
        tid = db.add_table("ventas", ["fecha", "producto", "cantidad", "precio_unitario", "total", "cliente", "metodo_pago"],
                           [{"fecha": "2026-01-01", "producto": "Zeta", "cantidad": 1, "total": 10}],
                           display_name="Ventas", column_types={"fecha": "date"})
        assert onto.read_sheet_meta(db.columns_of(tid)) is None
        _, done = await analyze_and_commit(ORG_A, lambda: [csv_up("ventas.csv", VENTAS_CSV)])
        assert done["results"][0]["status"] == "appended" and done["results"][0]["table_id"] == str(tid)
        cols = db.columns_of(tid)
        assert onto.read_sheet_meta(cols)["kind"] == "ventas"
        assert onto.column_roles(cols)["total"]["role"] == "total"
        assert len(db.rows_of(tid)) == 4

    async def test_el_rol_manda_sobre_el_nombre_al_sumar(self, dbs):
        # la tabla ya guardada llama "costo" a lo que el archivo nuevo llama "Vlr Compra"
        await analyze_and_commit(ORG_A, lambda: [csv_up("lista.csv", "Nombre,Costo,Stock\nGasas,900,10\n")])
        nuevo = "Nombre,Vlr Compra,Stock\nJeringas,500,20\n"
        proposal = await intake.analyze_uploads(ORG_A, [csv_up("lista2.csv", nuevo)])
        assert sheets_of(proposal)[0]["destination"]["action"] == "append"
        done = await intake.commit_uploads(ORG_A, [csv_up("lista2.csv", nuevo)], plan_from(proposal))
        assert done["results"][0]["status"] == "appended"
        db = dbs.db(ORG_A)
        tid = next(iter(db.tables))
        assert [c["name"] for c in db.columns_of(tid)] == ["nombre", "costo", "stock"]     # no crea 'vlr_compra'
        assert db.rows_of(tid)[1] == {"nombre": "Jeringas", "costo": 500, "stock": 20}

    async def test_columna_nueva_se_declara_con_su_rol_sin_pisar_los_existentes(self, dbs):
        await analyze_and_commit(ORG_A, lambda: [csv_up("v.csv", VENTAS_CSV)])
        nuevo = VENTAS_CSV.replace("Cliente", "Cliente,Metodo Pago").replace("Ana", "Ana,Efectivo").replace("Luis", "Luis,Nequi")
        proposal = await intake.analyze_uploads(ORG_A, [csv_up("v2.csv", nuevo)])
        done = await intake.commit_uploads(ORG_A, [csv_up("v2.csv", nuevo)], plan_from(proposal))
        assert done["results"][0]["status"] == "appended"
        cols = dbs.db(ORG_A).columns_of(next(iter(dbs.db(ORG_A).tables)))
        assert onto.column_roles(cols)["metodo_pago"]["role"] == "metodo_pago"

    async def test_hoja_omitida_y_hoja_vacia(self, dbs):
        proposal = await intake.analyze_uploads(ORG_A, [csv_up("v.csv", VENTAS_CSV)])
        plan = plan_from(proposal)
        plan[0]["action"] = "skip"
        done = await intake.commit_uploads(ORG_A, [csv_up("v.csv", VENTAS_CSV)], plan)
        assert done["results"][0]["status"] == "skipped" and dbs.db(ORG_A).tables == {}

    async def test_commit_nunca_llama_al_modelo(self, dbs, _env):
        _env.GOOGLE_API_KEY = "AIzaSyFAKEKEYFAKEKEYFAKEKEYFAKEKEY12345"
        plan = [{"file_name": "hoja.csv", "sheet_name": None, "action": "create", "display_name": "Mi hoja"}]
        with patch("google.genai.Client", side_effect=AssertionError("commit no debe usar el modelo")):
            done = await intake.commit_uploads(ORG_A, [csv_up("hoja.csv", TestAgenteConModelo.GENERICA)], plan)
        assert done["results"][0]["status"] == "created" and done["results"][0]["display_name"] == "Mi hoja"

    async def test_falla_de_una_hoja_no_tumba_a_las_demas_y_no_deja_tabla_huerfana(self, dbs):
        up1, up2 = csv_up("ventas.csv", VENTAS_CSV), csv_up("inv.csv", INVENTARIO_CSV)
        proposal = await intake.analyze_uploads(ORG_A, [up1, up2])
        plan = plan_from(proposal)
        db = dbs.db(ORG_A)
        db.fail_when = lambda q, a: q.startswith("insert into org_data_rows") and "Gasas" in str(a) and "1500" in str(a) and "ana" in str(a).lower()
        done = await intake.commit_uploads(ORG_A, [csv_up("ventas.csv", VENTAS_CSV), csv_up("inv.csv", INVENTARIO_CSV)], plan)
        db.fail_when = None
        assert [r["status"] for r in done["results"]] == ["error", "created"]
        assert "No pude guardar" in done["results"][0]["message"] and "Traceback" not in json.dumps(done)
        assert [t["table_name"] for t in db.tables.values()] == ["inv"]


class TestCommitValidacionEstricta:
    async def _try(self, dbs, **over):
        item = {"file_name": "v.csv", "sheet_name": None, "action": "create", "kind": "ventas", "display_name": "V",
                "columns": [{"name": "fecha", "role": "fecha"}, {"name": "producto", "role": "producto"},
                            {"name": "cantidad", "role": "cantidad"}, {"name": "precio_unitario", "role": "precio_unitario"},
                            {"name": "total", "role": "total"}, {"name": "cliente", "role": "cliente"}]}
        item.update(over)
        done = await intake.commit_uploads(ORG_A, [csv_up("v.csv", VENTAS_CSV)], [item])
        return done["results"][0]

    async def test_caso_base_valido(self, dbs):
        assert (await self._try(dbs))["status"] == "created"

    @pytest.mark.parametrize("over,code", [
        ({"kind": "hackeo"}, "invalid_kind"),
        ({"columns": [{"name": "fecha", "role": "costo_unitario"}]}, "invalid_role"),
        ({"columns": [{"name": "fecha", "role": "fecha; DROP TABLE x"}]}, "invalid_role"),
        ({"columns": [{"name": "fecha", "role": "fecha"}, {"name": "total", "role": "fecha"}]}, "duplicate_role"),
        ({"columns": [{"name": "no_existe", "role": "fecha"}]}, "unknown_column"),
        ({"action": "borrar_todo"}, "invalid_action"),
    ])
    async def test_entradas_invalidas_dan_error_humano_y_no_guardan(self, dbs, over, code):
        r = await self._try(dbs, **over)
        assert r["status"] == "error" and r["error"]["code"] == code and r["message"]
        assert dbs.db(ORG_A).tables == {}

    async def test_hoja_inexistente_en_los_archivos(self, dbs):
        r = await self._try(dbs, sheet_name="Fantasma")
        assert r["error"]["code"] == "sheet_not_found"

    async def test_append_a_tabla_de_otra_org_no_existe(self, dbs):
        tid = dbs.db(ORG_B).add_table("ventas", ["fecha", "producto", "cantidad", "total"], [], display_name="V")
        r = await self._try(dbs, action="append", table_id=str(tid))
        assert r["error"]["code"] == "table_not_found"
        assert dbs.db(ORG_B).rows_of(tid) == []

    @pytest.mark.parametrize("tid", ["no-es-uuid", "'; DROP TABLE x;--", "00000000-0000-0000-0000-000000000000", ""])
    async def test_ids_mal_formados_o_inexistentes(self, dbs, tid):
        r = await self._try(dbs, action="append", table_id=tid)
        assert r["status"] == "error" and r["error"]["code"] in ("table_not_found", "invalid_action")

    async def test_append_de_otra_clase_se_rechaza_sin_mezclar(self, dbs):
        await analyze_and_commit(ORG_A, lambda: [csv_up("inventario.csv", INVENTARIO_CSV)])
        inv_id = str(next(iter(dbs.db(ORG_A).tables)))
        r = await self._try(dbs, action="append", table_id=inv_id)
        assert r["error"]["code"] == "kind_mismatch" and "no las mezclo" in r["message"]
        assert len(dbs.db(ORG_A).rows_of(next(iter(dbs.db(ORG_A).tables)))) == 2

    async def test_append_a_hoja_del_mismo_cargue_que_no_se_guardo(self, dbs):
        r = await self._try(dbs, action="append", into_sheet="otra.csv::")
        assert r["error"]["code"] == "target_not_saved"

    async def test_sin_plan_o_archivo_duplicado(self, dbs):
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            await intake.commit_uploads(ORG_A, [csv_up("v.csv", VENTAS_CSV)], [])
        done = await intake.commit_uploads(ORG_A, [csv_up("v.csv", VENTAS_CSV), csv_up("v.csv", VENTAS_CSV)],
                                           [{"file_name": "v.csv", "sheet_name": None, "action": "create"}])
        assert done["results"][0]["error"]["code"] == "duplicate_file"

    async def test_nombre_con_inyeccion_se_sanea(self, dbs):
        r = await self._try(dbs, display_name="x'); DROP TABLE org_data_tables;--\n\x00")
        assert r["status"] == "created"
        t = next(iter(dbs.db(ORG_A).tables.values()))
        assert "\n" not in t["display_name"] and "\x00" not in t["display_name"]
        assert t["table_name"].replace("_", "").isalnum()


# ---------------------------------------------------------------------------
# roles
# ---------------------------------------------------------------------------

class TestCorregirRoles:
    async def _hoja_generica(self, dbs):
        _, done = await analyze_and_commit(ORG_A, lambda: [csv_up("hoja.csv", TestAgenteConModelo.GENERICA)])
        return done["results"][0]["table_id"]

    async def test_el_duenio_corrige_y_queda_como_verdad(self, dbs):
        tid = await self._hoja_generica(dbs)
        res = await intake.update_table_roles(ORG_A, tid, {"c1": "fecha", "c2": "producto", "c3": "cantidad", "c4": "total"}, "ventas")
        assert res["kind"] == "ventas" and res["mapping_source"] == "user"
        assert {c["name"]: c["role"] for c in res["columns"]} == {"c1": "fecha", "c2": "producto", "c3": "cantidad", "c4": "total"}
        cols = dbs.db(ORG_A).columns_of(next(iter(dbs.db(ORG_A).tables)))
        assert onto.read_sheet_meta(cols)["mapping_source"] == "user"

    async def test_la_cache_de_firma_se_recalcula_y_la_siguiente_hoja_sale_corregida_sin_modelo(self, dbs, _env):
        tid = await self._hoja_generica(dbs)
        await intake.update_table_roles(ORG_A, tid, {"c1": "fecha", "c2": "producto", "c3": "cantidad", "c4": "total"}, "ventas")
        _env.GOOGLE_API_KEY = "AIzaSyFAKEKEYFAKEKEYFAKEKEYFAKEKEY12345"
        with patch("google.genai.Client", side_effect=AssertionError("no debe llamar al modelo")):
            r = await intake.analyze_uploads(ORG_A, [csv_up("hoja_nueva.csv", TestAgenteConModelo.GENERICA)])
        s = sheets_of(r)[0]
        assert s["kind"] == "ventas" and s["mapping_source"] == "user" and s["needs_review"] is False
        assert [c["role"] for c in s["columns"]] == ["fecha", "producto", "cantidad", "total"]
        assert s["destination"]["action"] == "append"           # ya es la misma clase y estructura

    async def test_correccion_tambien_vive_sin_memoria_en_la_propia_tabla(self, dbs, _env):
        tid = await self._hoja_generica(dbs)
        await intake.update_table_roles(ORG_A, tid, {"c4": "total"}, "ventas")
        ai.clear_memory_cache()
        _env.GOOGLE_API_KEY = "AIzaSyFAKEKEYFAKEKEYFAKEKEYFAKEKEY12345"
        with patch("google.genai.Client", side_effect=AssertionError("no debe llamar al modelo")):
            s = sheets_of(await intake.analyze_uploads(ORG_A, [csv_up("n.csv", TestAgenteConModelo.GENERICA)]))[0]
        assert [c["role"] for c in s["columns"]][3] == "total"

    async def test_rol_repetido_se_rechaza_con_mensaje_humano(self, dbs):
        tid = await self._hoja_generica(dbs)
        with pytest.raises(intake.IntakeError) as e:
            await intake.update_table_roles(ORG_A, tid, {"c1": "fecha", "c2": "fecha"}, "ventas")
        assert e.value.code == "duplicate_role" and "Fecha de la venta" in e.value.message

    @pytest.mark.parametrize("roles,kind,code", [
        ({"c1": "costo_unitario"}, "ventas", "invalid_role"),
        ({"c1": "fecha"}, "inventado", "invalid_kind"),
        ({"zzz": "fecha"}, "ventas", "unknown_column"),
        ({"c1": "fecha"}, "otro", "invalid_role"),
    ])
    async def test_validacion_por_listas_blancas(self, dbs, roles, kind, code):
        tid = await self._hoja_generica(dbs)
        with pytest.raises(intake.IntakeError) as e:
            await intake.update_table_roles(ORG_A, tid, roles, kind)
        assert e.value.code == code

    async def test_none_significa_dato_adicional_y_cambiar_el_tipo_descarta_roles_que_ya_no_valen(self, dbs):
        tid = await self._hoja_generica(dbs)
        await intake.update_table_roles(ORG_A, tid, {"c1": "fecha", "c4": "precio_unitario"}, "ventas")
        res = await intake.update_table_roles(ORG_A, tid, {}, "compras")
        roles = {c["name"]: c["role"] for c in res["columns"]}
        assert roles["c1"] == "fecha" and roles["c4"] == "otro"        # precio_unitario no existe en compras
        res = await intake.update_table_roles(ORG_A, tid, {"c1": None}, None)
        assert {c["name"]: c["role"] for c in res["columns"]}["c1"] == "otro"

    async def test_tabla_de_otra_organizacion_o_inexistente(self, dbs):
        tid = await self._hoja_generica(dbs)
        for org, table in ((ORG_B, tid), (ORG_A, "00000000-0000-0000-0000-000000000000"), (ORG_A, "basura")):
            with pytest.raises(intake.IntakeError) as e:
                await intake.update_table_roles(org, table, {"c1": "fecha"}, "ventas")
            assert e.value.code == "not_found"

    async def test_tabla_vieja_sin_metadata_se_puede_corregir(self, dbs):
        tid = dbs.db(ORG_A).add_table("ventas", ["fecha", "producto", "cantidad", "total"], [])
        res = await intake.update_table_roles(ORG_A, str(tid), {"total": "total"}, None)
        assert res["kind"] == "ventas" and res["mapping_source"] == "user"


# ---------------------------------------------------------------------------
# deshacer una carga que se sumo a una hoja existente
# ---------------------------------------------------------------------------

class TestDeshacerCarga:
    async def _dos_cargas(self, dbs):
        await analyze_and_commit(ORG_A, lambda: [csv_up("ventas mayo.csv", VENTAS_CSV)])
        nuevo = VENTAS_CSV.replace("Ana", "Eva")
        _, done = await analyze_and_commit(ORG_A, lambda: [csv_up("ventas nov.csv", nuevo)])
        return done["results"][0]

    async def test_la_carga_sumada_devuelve_como_deshacerla(self, dbs):
        r = await self._dos_cargas(dbs)
        assert r["status"] == "appended" and r["undo"]["action"] == "delete_rows"
        assert r["undo"]["table_id"] == r["table_id"] and r["undo"]["loaded_at"] == r["loaded_at"]

    async def test_deshacer_borra_solo_las_filas_de_esa_carga(self, dbs):
        r = await self._dos_cargas(dbs)
        tid = next(iter(dbs.db(ORG_A).tables))
        assert len(dbs.db(ORG_A).rows_of(tid)) == 6
        res = await intake.undo_commit_load(ORG_A, r["table_id"], r["undo"]["loaded_at"])
        assert res == {"table_id": r["table_id"], "rows_deleted": 3, "total_rows": 3}
        rows = dbs.db(ORG_A).rows_of(tid)
        assert len(rows) == 3 and all(x["cliente"] != "Eva" for x in rows) and dbs.db(ORG_A).tables[tid]["row_count"] == 3
        assert len(dbs.db(ORG_A).records) == 3                     # tambien las filas legacy de esa carga

    async def test_deshacer_dos_veces_no_borra_nada_mas(self, dbs):
        r = await self._dos_cargas(dbs)
        await intake.undo_commit_load(ORG_A, r["table_id"], r["undo"]["loaded_at"])
        again = await intake.undo_commit_load(ORG_A, r["table_id"], r["undo"]["loaded_at"])
        assert again["rows_deleted"] == 0 and again["total_rows"] == 3

    @pytest.mark.parametrize("stamp", ["ayer", "", "2026-10-19", "2026-10-19T12:00:00", "'; DROP TABLE x;--"])
    async def test_marca_invalida_se_rechaza(self, dbs, stamp):
        r = await self._dos_cargas(dbs)
        with pytest.raises(intake.IntakeError) as e:
            await intake.undo_commit_load(ORG_A, r["table_id"], stamp)
        assert e.value.code == "invalid_load"
        assert dbs.db(ORG_A).tables[next(iter(dbs.db(ORG_A).tables))]["row_count"] == 6

    async def test_otra_organizacion_o_tabla_inexistente(self, dbs):
        r = await self._dos_cargas(dbs)
        for org, tid in ((ORG_B, r["table_id"]), (ORG_A, "00000000-0000-0000-0000-000000000000"), (ORG_A, "basura")):
            with pytest.raises(intake.IntakeError) as e:
                await intake.undo_commit_load(org, tid, r["undo"]["loaded_at"])
            assert e.value.code == "not_found"
        assert dbs.db(ORG_A).tables[next(iter(dbs.db(ORG_A).tables))]["row_count"] == 6

    async def test_la_marca_manda_solo_se_deshace_la_carga_que_la_tiene(self, dbs):
        r = await self._dos_cargas(dbs)
        primera_marca = dbs.db(ORG_A).rows[0]["created_at"].isoformat()
        assert primera_marca != r["loaded_at"]
        res = await intake.undo_commit_load(ORG_A, r["table_id"], primera_marca)
        assert res["rows_deleted"] == 3 and res["total_rows"] == 3
        assert {x["created_at"].isoformat() for x in dbs.db(ORG_A).rows} == {r["loaded_at"]}     # quedo la segunda carga
