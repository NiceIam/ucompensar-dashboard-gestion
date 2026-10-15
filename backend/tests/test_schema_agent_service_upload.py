"""Unit tests de carga de datos y smart_upload (schema_agent_service) — PI0320251.

Tests:
- load_csv_to_table: filas, NaN, mapeo de columnas, transaccion, aislamiento por org
- smart_upload: tabla nueva vs existente (umbral 0.5), columnas faltantes, casos limite
- Flujo completo archivo -> parse_file_sheets -> smart_upload para CSV, Excel
  (una y varias hojas), JSON y archivos corruptos

La BD se emula con tests/fake_org_db.py; no hay Postgres ni Gemini reales.
"""

import io
import json
import os
import warnings
from types import SimpleNamespace
from unittest.mock import patch

import openpyxl
import pandas as pd
import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.datastructures import UploadFile

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

TEN_COLS = ["nombre", "apellido", "ciudad", "telefono", "correo", "pais", "barrio", "edad", "genero", "cargo"]


@pytest.fixture
def org_dbs():
    dbs = FakeOrgDBs()
    with patch("app.services.schema_agent_service.get_org_pool", dbs.get_org_pool):
        yield dbs


@pytest.fixture(autouse=True)
def _silence_pandas_date_inference_warnings():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        yield


def _upload(content: bytes, filename: str, content_type: str = "") -> UploadFile:
    headers = Headers({"content-type": content_type}) if content_type else None
    return UploadFile(file=io.BytesIO(content), filename=filename, headers=headers)


def _xlsx(sheets: dict[str, list[list]]) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(title=name)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# load_csv_to_table
# ---------------------------------------------------------------------------

class TestLoadCsvToTable:
    @pytest.mark.asyncio
    async def test_inserta_filas_omite_nulos_y_actualiza_row_count(self, org_dbs):
        from app.services.schema_agent_service import load_csv_to_table

        db = org_dbs.db(ORG_A)
        tid = db.add_table("t", ["nombre", "nota"])
        df = pd.DataFrame({"Nombre": ["Ana", "Luis"], "Nota": ["ok", None]})

        result = await load_csv_to_table(df, ORG_A, str(tid))

        assert result["rows_inserted"] == 2
        assert result["total_rows"] == 2
        assert db.rows_of(tid) == [{"nombre": "Ana", "nota": "ok"}, {"nombre": "Luis"}]
        assert db.tables[tid]["row_count"] == 2
        assert len(db.records) == 2  # espejo en data_records legacy

    @pytest.mark.asyncio
    async def test_cargas_sucesivas_acumulan_total(self, org_dbs):
        from app.services.schema_agent_service import load_csv_to_table

        db = org_dbs.db(ORG_A)
        tid = db.add_table("t", ["a"], rows=[{"a": "previo"}])

        result = await load_csv_to_table(pd.DataFrame({"a": ["x", "y"]}), ORG_A, str(tid))

        assert result["rows_inserted"] == 2
        assert result["total_rows"] == 3
        assert db.tables[tid]["row_count"] == 3

    @pytest.mark.asyncio
    async def test_column_mapping_renombra_antes_de_limpiar(self, org_dbs):
        from app.services.schema_agent_service import load_csv_to_table

        db = org_dbs.db(ORG_A)
        tid = db.add_table("t", ["nombre"])

        await load_csv_to_table(pd.DataFrame({"Full Name": ["Ana"]}), ORG_A, str(tid), {"Full Name": "Nombre"})

        assert db.rows_of(tid) == [{"nombre": "Ana"}]

    @pytest.mark.asyncio
    async def test_dataframe_vacio_no_inserta_pero_responde(self, org_dbs):
        from app.services.schema_agent_service import load_csv_to_table

        db = org_dbs.db(ORG_A)
        tid = db.add_table("t", ["a"])

        result = await load_csv_to_table(pd.DataFrame(columns=["a"]), ORG_A, str(tid))

        assert result["rows_inserted"] == 0
        assert result["total_rows"] == 0

    @pytest.mark.asyncio
    async def test_preserva_unicode_y_convierte_fechas_a_texto(self, org_dbs):
        from app.services.schema_agent_service import load_csv_to_table

        db = org_dbs.db(ORG_A)
        tid = db.add_table("t", ["paciente", "fecha"])
        df = pd.DataFrame({"paciente": ["Muñoz Peña"], "fecha": pd.to_datetime(["2024-03-01"])})

        await load_csv_to_table(df, ORG_A, str(tid))

        assert db.rows_of(tid) == [{"paciente": "Muñoz Peña", "fecha": "2024-03-01 00:00:00"}]

    @pytest.mark.asyncio
    async def test_tabla_inexistente_no_inserta_nada(self, org_dbs):
        from app.services.schema_agent_service import load_csv_to_table

        db = org_dbs.db(ORG_A)

        result = await load_csv_to_table(pd.DataFrame({"a": ["x"]}), ORG_A, "00000000-0000-4000-8000-000000000000")

        assert result == {"error": "Tabla no encontrada"}
        assert db.rows == [] and db.records == []

    @pytest.mark.asyncio
    async def test_aislamiento_no_carga_en_tabla_de_otra_org(self, org_dbs):
        from app.services.schema_agent_service import load_csv_to_table

        db_b = org_dbs.db(ORG_B)
        tid_b = db_b.add_table("t", ["a"])
        org_dbs.db(ORG_A)

        result = await load_csv_to_table(pd.DataFrame({"a": ["x"]}), ORG_A, str(tid_b))

        assert "error" in result
        assert db_b.rows_of(tid_b) == []

    @pytest.mark.asyncio
    async def test_fallo_a_mitad_de_archivo_revierte_todo(self, org_dbs):
        """Transaccion: si la fila 3 falla, no quedan filas 1-2 ni registros legacy ni row_count nuevo."""
        from app.services.schema_agent_service import load_csv_to_table

        db = org_dbs.db(ORG_A)
        tid = db.add_table("t", ["a"], rows=[{"a": "previo"}])
        db.fail_when = lambda q, args: q.startswith("insert into org_data_rows") and '"c3"' in args[1]
        df = pd.DataFrame({"a": ["c1", "c2", "c3", "c4"]})

        with pytest.raises(Exception):
            await load_csv_to_table(df, ORG_A, str(tid))

        assert db.rows_of(tid) == [{"a": "previo"}]
        assert db.records == []
        assert db.tables[tid]["row_count"] == 1

    @pytest.mark.xfail(
        strict=True,
        reason="schema_agent_service.py:398-401 isinstance(val,(int,float)) es False para numpy.int64: un "
               "DataFrame solo con enteros se guarda como strings ('5'); con otra columna decimal los "
               "enteros salen como float (5.0) por el upcast de iterrows()",
    )
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "df",
        [
            pd.DataFrame({"cantidad": [5, 7], "stock": [1, 2]}),
            pd.DataFrame({"cantidad": [5, 7], "precio": [1.5, 2.5]}),
        ],
    )
    async def test_enteros_se_guardan_como_enteros(self, org_dbs, df):
        from app.services.schema_agent_service import load_csv_to_table

        db = org_dbs.db(ORG_A)
        tid = db.add_table("t", list(df.columns))

        await load_csv_to_table(df, ORG_A, str(tid))

        assert type(db.rows_of(tid)[0]["cantidad"]) is int

    @pytest.mark.xfail(
        strict=True,
        reason="schema_agent_service.py:396-407 pd.isna(val) sobre una lista (JSON anidado) devuelve un array y "
               "`if array` lanza ValueError: [{'id':1,'tags':['a','b']}] aborta la carga",
    )
    @pytest.mark.asyncio
    async def test_celdas_con_listas_de_json_anidado(self, org_dbs):
        from app.services.schema_agent_service import load_csv_to_table

        db = org_dbs.db(ORG_A)
        tid = db.add_table("t", ["id", "tags"])
        df = pd.DataFrame([{"id": "1", "tags": ["a", "b"]}])

        result = await load_csv_to_table(df, ORG_A, str(tid))

        assert result["rows_inserted"] == 1

    @pytest.mark.xfail(
        strict=True,
        reason="schema_agent_service.py:399,406 float('inf') pasa como numero y json.dumps emite 'Infinity', "
               "que jsonb de Postgres rechaza: una sola celda inf aborta (y revierte) todo el archivo",
    )
    @pytest.mark.asyncio
    async def test_valores_infinitos_no_rompen_la_carga(self, org_dbs):
        from app.services.schema_agent_service import load_csv_to_table

        db = org_dbs.db(ORG_A)
        tid = db.add_table("t", ["ratio", "n"])
        df = pd.DataFrame({"ratio": [float("inf"), 1.5], "n": ["a", "b"]})

        result = await load_csv_to_table(df, ORG_A, str(tid))

        assert result["rows_inserted"] == 2

    @pytest.mark.xfail(
        strict=True,
        reason="schema_agent_service.py:386-394 'Nombre' y 'nombre' limpian al mismo nombre; row[col] devuelve "
               "una Serie y pd.isna(Serie) lanza ValueError. Falla despues de create_table",
    )
    @pytest.mark.asyncio
    async def test_encabezados_que_colisionan_al_limpiar(self, org_dbs):
        from app.services.schema_agent_service import load_csv_to_table

        db = org_dbs.db(ORG_A)
        tid = db.add_table("t", ["nombre"])
        df = pd.DataFrame([["Ana", "Luis"]], columns=["Nombre", "nombre"])

        result = await load_csv_to_table(df, ORG_A, str(tid))

        assert result["rows_inserted"] == 1


# ---------------------------------------------------------------------------
# smart_upload
# ---------------------------------------------------------------------------

class TestSmartUpload:
    @pytest.mark.asyncio
    async def test_crea_tabla_nueva_cuando_no_hay_match(self, org_dbs):
        from app.services.schema_agent_service import smart_upload

        df = pd.DataFrame({
            "Producto": ["Gasas", "Jeringas"],
            "Precio Venta": [1500, 800],
            "Stock": [10, 20],
        })

        result = await smart_upload(df, ORG_A, "inventario.csv")

        db = org_dbs.db(ORG_A)
        assert result["status"] == "created_new_table"
        assert result["table_name"] == "productos"
        assert result["rows_inserted"] == 2 and result["total_rows"] == 2
        tid = next(iter(db.tables))
        assert [c["name"] for c in db.columns_of(tid)] == ["producto", "precio_venta", "stock"]
        assert [a["action"] for a in result["actions"]] == ["create_table", "load_data"]
        assert db.tables[tid]["row_count"] == 2

    @pytest.mark.asyncio
    async def test_segunda_carga_con_mismas_columnas_va_a_la_tabla_existente(self, org_dbs):
        from app.services.schema_agent_service import smart_upload

        df = pd.DataFrame({"Producto": ["a"], "Precio Venta": ["1"], "Stock": ["2"]})
        primera = await smart_upload(df, ORG_A, "f1.csv")

        segunda = await smart_upload(df, ORG_A, "f2.csv")

        assert segunda["status"] == "loaded_to_existing"
        assert segunda["table_id"] == primera["table_id"]
        assert segunda["total_rows"] == 2
        assert len(org_dbs.db(ORG_A).tables) == 1

    @pytest.mark.asyncio
    async def test_agrega_columnas_faltantes_con_tipo_inferido(self, org_dbs):
        from app.services.schema_agent_service import smart_upload

        db = org_dbs.db(ORG_A)
        tid = db.add_table("personas", ["nombre", "ciudad", "edad"])
        df = pd.DataFrame({"nombre": ["Ana"], "ciudad": ["Cali"], "edad": [30], "puntaje": [4.5]})

        result = await smart_upload(df, ORG_A, "f.csv")

        assert result["status"] == "loaded_to_existing"
        assert [a["action"] for a in result["actions"]] == ["modify_table", "load_data"]
        nuevas = [c for c in db.columns_of(tid) if c["name"] == "puntaje"]
        assert nuevas == [{"name": "puntaje", "type": "number"}]
        assert db.rows_of(tid)[0]["puntaje"] == 4.5

    @pytest.mark.asyncio
    async def test_score_04_no_alcanza_para_reutilizar_tabla(self, org_dbs):
        """find_matching_table acepta desde 0.3 pero smart_upload exige >= 0.5."""
        from app.services.schema_agent_service import find_matching_table, smart_upload, analyze_csv

        db = org_dbs.db(ORG_A)
        existente = db.add_table("personas", TEN_COLS)
        df = pd.DataFrame({"nombre": ["Ana"], "edad": ["30"], "x1": ["a"], "x2": ["b"]})
        assert (await find_matching_table(ORG_A, analyze_csv(df)["columns"]))["match_score"] == 0.4

        result = await smart_upload(df, ORG_A, "f.csv")

        assert result["status"] == "created_new_table"
        assert result["table_id"] != str(existente)
        assert db.rows_of(existente) == []

    @pytest.mark.asyncio
    async def test_score_06_reutiliza_tabla(self, org_dbs):
        from app.services.schema_agent_service import smart_upload

        db = org_dbs.db(ORG_A)
        existente = db.add_table("personas", TEN_COLS)
        df = pd.DataFrame({"nombre": ["Ana"], "edad": ["30"], "pais": ["CO"]})

        result = await smart_upload(df, ORG_A, "f.csv")

        assert result["status"] == "loaded_to_existing"
        assert result["table_id"] == str(existente)
        assert result["match_score"] == 0.6

    @pytest.mark.asyncio
    async def test_aislamiento_no_reutiliza_tabla_de_otra_org(self, org_dbs):
        from app.services.schema_agent_service import smart_upload

        db_b = org_dbs.db(ORG_B)
        tid_b = db_b.add_table("personas", ["nombre", "ciudad", "edad"])
        df = pd.DataFrame({"nombre": ["Ana"], "ciudad": ["Cali"], "edad": ["30"]})

        result = await smart_upload(df, ORG_A, "f.csv")

        assert result["status"] == "created_new_table"
        assert db_b.rows_of(tid_b) == []
        assert len(org_dbs.db(ORG_A).tables) == 1
        assert set(org_dbs.requested_org_ids) == {ORG_A}

    @pytest.mark.asyncio
    async def test_solo_encabezados_crea_tabla_sin_filas(self, org_dbs):
        from app.services.schema_agent_service import smart_upload

        result = await smart_upload(pd.DataFrame(columns=["a", "b"]), ORG_A, "vacio.csv")

        assert result["rows_inserted"] == 0
        assert result["total_rows"] == 0

    @pytest.mark.asyncio
    async def test_columnas_duplicadas_de_pandas_se_conservan(self, org_dbs):
        """read_csv renombra 'a,a' a 'a','a.1': ambas columnas deben cargarse."""
        from app.services.schema_agent_service import smart_upload

        df = pd.read_csv(io.BytesIO(b"a,a,b\n1,2,3\n"))

        result = await smart_upload(df, ORG_A, "dup.csv")

        tid = next(iter(org_dbs.db(ORG_A).tables))
        assert result["rows_inserted"] == 1
        assert [c["name"] for c in org_dbs.db(ORG_A).columns_of(tid)] == ["a", "a.1", "b"]

    @pytest.mark.xfail(
        strict=True,
        reason="schema_agent_service.py:513-531 al chocar el nombre sugerido ('datos_importados') con una tabla "
               "existente NO relacionada, carga ahi sin modify_table: las filas nuevas quedan con claves que "
               "columns_definition no declara",
    )
    @pytest.mark.asyncio
    async def test_archivo_no_relacionado_no_se_mezcla_sin_declarar_sus_columnas(self, org_dbs):
        from app.services.schema_agent_service import smart_upload

        db = org_dbs.db(ORG_A)
        await smart_upload(pd.DataFrame({"foo": ["1"], "bar": ["2"]}), ORG_A, "a.csv")

        result = await smart_upload(pd.DataFrame({"zeta": ["9"], "omega": ["8"]}), ORG_A, "b.csv")

        tid = next(iter(db.tables))
        declaradas = {c["name"] for c in db.columns_of(tid)}
        claves = {k for fila in db.rows_of(tid) for k in fila}
        assert claves <= declaradas, f"claves sin declarar: {claves - declaradas} ({result['status']})"

    @pytest.mark.xfail(
        strict=True,
        reason="schema_agent_service.py:452-513 smart_upload no valida entrada: un DataFrame sin columnas "
               "(JSON '[]' o Excel con hoja en blanco) crea una tabla fantasma 'datos_importados' sin columnas",
    )
    @pytest.mark.asyncio
    async def test_dataframe_sin_columnas_no_crea_tabla(self, org_dbs):
        from app.services.schema_agent_service import smart_upload

        try:
            await smart_upload(pd.DataFrame(), ORG_A, "vacio.json")
        except (ValueError, HTTPException):
            pass

        assert org_dbs.db(ORG_A).tables == {}

    @pytest.mark.xfail(
        strict=True,
        reason="schema_agent_service.py:513-531 + 386-394 'Nombre'/'nombre' colisionan al limpiar: la carga "
               "revienta con ValueError despues de haber creado la tabla (queda huerfana)",
    )
    @pytest.mark.asyncio
    async def test_encabezados_que_colisionan_cargan_sin_error(self, org_dbs):
        from app.services.schema_agent_service import smart_upload

        df = pd.DataFrame([["Ana", "Luis"]], columns=["Nombre", "nombre"])

        result = await smart_upload(df, ORG_A, "f.csv")

        assert result["rows_inserted"] == 1


# ---------------------------------------------------------------------------
# Flujo completo: archivo -> parse -> smart_upload (router /schema/smart-upload)
# ---------------------------------------------------------------------------

def _user(org_id: str):
    return SimpleNamespace(org_id=org_id)


async def _router_upload(file: UploadFile, org_id: str = ORG_A) -> dict:
    from app.routers import schema as schema_router

    resp = await schema_router.smart_upload(file=file, current_user=_user(org_id))
    return json.loads(resp.body)


class TestSmartUploadEndToEnd:
    @pytest.mark.asyncio
    async def test_csv(self, org_dbs):
        csv = "Producto,Precio Venta,Stock\nGasas,1500,10\nJeringas,800,20\n".encode()

        body = await _router_upload(_upload(csv, "inv.csv", "text/csv"))

        assert body["status"] == "created_new_table"
        assert body["rows_inserted"] == 2
        assert "multi_sheet" not in body

    @pytest.mark.asyncio
    async def test_json_lista_con_claves_faltantes(self, org_dbs):
        data = json.dumps([{"producto": "a", "stock": 1}, {"producto": "b"}]).encode()

        body = await _router_upload(_upload(data, "d.json", "application/json"))

        db = org_dbs.db(ORG_A)
        tid = next(iter(db.tables))
        assert body["rows_inserted"] == 2
        assert {k for k in db.rows_of(tid)[1]} == {"producto"}  # NaN omitido, no 'null'

    @pytest.mark.asyncio
    async def test_json_objeto_unico_es_una_fila(self, org_dbs):
        body = await _router_upload(_upload(b'{"producto": "a", "stock": 3}', "d.json"))

        assert body["rows_inserted"] == 1

    @pytest.mark.asyncio
    async def test_excel_una_hoja_mantiene_forma_de_respuesta_simple(self, org_dbs):
        xlsx = _xlsx({"Hoja1": [["producto", "stock"], ["a", 1], ["b", 2]]})

        body = await _router_upload(_upload(xlsx, "a.xlsx"))

        assert body["status"] == "created_new_table"
        assert body["rows_inserted"] == 2
        assert "sheets" not in body

    @pytest.mark.asyncio
    async def test_excel_varias_hojas_procesa_cada_una(self, org_dbs):
        xlsx = _xlsx({
            "Clientes": [["nombre", "empresa", "telefono"], ["Ana", "X", "300"]],
            "Empleados": [["empleado", "cargo", "salario"], ["Luis", "Medico", 5000], ["Eva", "Enfermera", 3000]],
        })

        body = await _router_upload(_upload(xlsx, "plantilla.xlsx"))

        db = org_dbs.db(ORG_A)
        assert body["multi_sheet"] is True
        assert body["sheets_processed"] == 2
        assert body["total_rows_inserted"] == 3
        assert [s["sheet_name"] for s in body["sheets"]] == ["Clientes", "Empleados"]
        assert {t["table_name"] for t in db.tables.values()} == {"clientes", "empleados"}

    @pytest.mark.asyncio
    async def test_excel_hoja_vacia_se_omite_sin_afectar_las_demas(self, org_dbs):
        xlsx = _xlsx({
            "Datos": [["producto", "stock"], ["a", 1]],
            "Vacia": [["producto", "stock"]],  # solo encabezados
        })

        body = await _router_upload(_upload(xlsx, "a.xlsx"))

        estados = {s["sheet_name"]: s["status"] for s in body["sheets"]}
        assert estados["Vacia"] == "skipped_empty"
        assert estados["Datos"] == "created_new_table"
        assert body["total_rows_inserted"] == 1

    @pytest.mark.asyncio
    async def test_excel_hoja_que_falla_no_aborta_las_otras(self, org_dbs):
        xlsx = _xlsx({
            "Mala": [["producto", "stock"], ["BOOM", 1]],
            "Buena": [["empleado", "cargo", "salario"], ["Luis", "Medico", 5000]],
        })
        org_dbs.db(ORG_A).fail_when = lambda q, args: q.startswith("insert into org_data_rows") and "BOOM" in args[1]

        body = await _router_upload(_upload(xlsx, "a.xlsx"))

        estados = {s["sheet_name"]: s["status"] for s in body["sheets"]}
        assert estados == {"Mala": "error", "Buena": "created_new_table"}
        assert body["total_rows_inserted"] == 1
        assert org_dbs.db(ORG_A).rows and all("BOOM" not in str(r["data"]) for r in org_dbs.db(ORG_A).rows)

    @pytest.mark.asyncio
    async def test_excel_hojas_con_igual_estructura_se_apilan_en_una_tabla(self, org_dbs):
        """Las hojas se procesan en serie: la 2da ve la tabla que creo la 1ra."""
        xlsx = _xlsx({
            "Enero": [["producto", "stock", "codigo"], ["a", 1, "x"]],
            "Febrero": [["producto", "stock", "codigo"], ["b", 2, "y"]],
        })

        body = await _router_upload(_upload(xlsx, "meses.xlsx"))

        assert [s["status"] for s in body["sheets"]] == ["created_new_table", "loaded_to_existing"]
        assert len(org_dbs.db(ORG_A).tables) == 1
        assert body["total_rows_inserted"] == 2

    # -- archivos invalidos ----------------------------------------------------

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "content, filename",
        [
            (b"", "vacio.csv"),                          # EmptyDataError
            (b"\n\n", "blancos.csv"),
            (b"esto no es un xlsx", "roto.xlsx"),        # zip invalido
            (b"{no es json", "malo.json"),
            (b"PK\x03\x04basura", "falso.xlsx"),
        ],
    )
    async def test_archivo_corrupto_o_vacio_responde_422_sin_escribir_en_bd(self, org_dbs, content, filename):
        with pytest.raises(HTTPException) as exc_info:
            await _router_upload(_upload(content, filename))

        assert exc_info.value.status_code == 422
        assert org_dbs.requested_org_ids == []

    @pytest.mark.asyncio
    async def test_extension_no_soportada_responde_422(self, org_dbs):
        with pytest.raises(HTTPException) as exc_info:
            await _router_upload(_upload(b"a,b\n1,2\n", "datos.txt"))

        assert exc_info.value.status_code == 422

    @pytest.mark.xfail(
        strict=True,
        reason="file_service.py:66,113 pd.read_csv sin encoding: un CSV exportado en latin-1 (tipico de Excel "
               "en Colombia, 'Cédula', 'Año') falla con UnicodeDecodeError y se rechaza con 422",
    )
    @pytest.mark.asyncio
    async def test_csv_latin1(self, org_dbs):
        csv = "cédula,año\n123,2024\n".encode("latin-1")

        body = await _router_upload(_upload(csv, "datos.csv", "text/csv"))

        assert body["rows_inserted"] == 1

    @pytest.mark.xfail(
        strict=True,
        reason="file_service.py:66,113 pd.read_csv usa sep=',': un CSV con ';' (Excel en configuracion regional "
               "es-CO) se lee como UNA sola columna 'a;b;c'",
    )
    @pytest.mark.asyncio
    async def test_csv_separado_por_punto_y_coma(self, org_dbs):
        body = await _router_upload(_upload(b"nombre;edad;ciudad\nAna;30;Cali\n", "datos.csv", "text/csv"))

        assert body["analysis"]["column_count"] == 3
