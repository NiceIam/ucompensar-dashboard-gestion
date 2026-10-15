"""Unit tests for schema_agent_service (analisis, matching, create/modify) — PI0320251.

Tests:
- analyze_csv / _infer_column_type: inferencia de tipos y metadata de columnas
- _suggest_table_name: heuristica de nombre de tabla
- find_matching_table: umbrales de similitud, sin match, empate, aislamiento por org
- create_table / modify_table: idempotencia y manejo de columnas

Borrado y carga/smart_upload estan en test_schema_agent_service_delete.py y
test_schema_agent_service_upload.py. La BD se emula con tests/fake_org_db.py
(nunca se toca Postgres ni Gemini).
"""

import json
import os
import uuid
import warnings
from unittest.mock import patch

import pandas as pd
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
    """FakeOrgDBs instalado como get_org_pool del servicio."""
    dbs = FakeOrgDBs()
    with patch("app.services.schema_agent_service.get_org_pool", dbs.get_org_pool):
        yield dbs


@pytest.fixture(autouse=True)
def _silence_pandas_date_inference_warnings():
    """to_datetime emite UserWarning al inferir formato en texto libre; es ruido."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        yield


def _cols(*names: str) -> list[dict]:
    """Columnas en el formato que produce analyze_csv()['columns']."""
    return [{"clean_name": n} for n in names]


# 10 nombres sin parecido entre si (ningun par supera sim 0.8)
TEN_COLS = ["nombre", "apellido", "ciudad", "telefono", "correo", "pais", "barrio", "edad", "genero", "cargo"]


# ---------------------------------------------------------------------------
# _infer_column_type
# ---------------------------------------------------------------------------

class TestInferColumnType:
    """El tipo se decide primero por nombre (hint) y luego por contenido."""

    @pytest.mark.parametrize(
        "name, values, expected",
        [
            ("fecha_cita", ["no es fecha"], "date"),       # el hint por nombre gana al contenido
            ("precio_venta", ["abc"], "number"),
            ("cantidad", ["abc"], "integer"),
            ("activo", ["abc"], "boolean"),
            ("nombre", [1, 2, 3], "text"),                 # hint de texto gana a contenido numerico
        ],
    )
    def test_hint_por_nombre_tiene_prioridad(self, name, values, expected):
        from app.services.schema_agent_service import _infer_column_type

        assert _infer_column_type(name, pd.Series(values)) == expected

    @pytest.mark.parametrize(
        "values, expected",
        [
            ([1, 2, 3], "integer"),
            ([1.5, 2, 3], "number"),
            (["10", "20", "30"], "integer"),
            (["10.5", "20", "30"], "number"),
            (["2024-01-15", "2024-02-01", "2024-03-09"], "date"),
            (["15/01/2024", "01/02/2024", "09/03/2024"], "date"),
            (["si", "no", "si", "no"], "boolean"),
            (["true", "false", "True", "FALSE"], "boolean"),
            (["gripe", "asma", "migraña"], "text"),
        ],
    )
    def test_inferencia_por_contenido(self, values, expected):
        from app.services.schema_agent_service import _infer_column_type

        assert _infer_column_type("col_x", pd.Series(values)) == expected

    def test_serie_vacia_es_text(self):
        from app.services.schema_agent_service import _infer_column_type

        assert _infer_column_type("col_x", pd.Series([], dtype=object)) == "text"

    def test_umbral_80_por_ciento_numerico(self):
        """5 de 6 numericos (83%) -> numerico; 4 de 6 (67%) -> no numerico."""
        from app.services.schema_agent_service import _infer_column_type

        assert _infer_column_type("col_x", pd.Series(["1", "2", "3", "4", "5", "x"])) == "integer"
        assert _infer_column_type("col_x", pd.Series(["1", "2", "3", "4", "x", "y"])) == "text"

    def test_negativos_y_notacion_cientifica_son_numericos(self):
        from app.services.schema_agent_service import _infer_column_type

        assert _infer_column_type("col_x", pd.Series(["-5", "-10", "3"])) == "integer"
        assert _infer_column_type("col_x", pd.Series(["1e3", "2.5e-1"])) == "number"

    def test_nombre_con_subcadena_de_hint_no_fuerza_tipo(self):
        from app.services.schema_agent_service import _infer_column_type

        assert _infer_column_type("diagnostico", pd.Series(["gripe", "asma", "migraña"])) == "text"

    def test_nombre_narrativa_no_es_numero(self):
        from app.services.schema_agent_service import _infer_column_type

        assert _infer_column_type("narrativa", pd.Series(["paciente estable", "sin cambios"])) == "text"

    @pytest.mark.parametrize(
        "name, expected",
        [
            # plural simple, sufijo numerico y raices pegadas (camelCase de JSON limpiado)
            ("fechas", "date"), ("fecha1", "date"), ("fecha2", "date"), ("periodos", "date"),
            ("fechanacimiento", "date"), ("fechacita", "date"),
            ("precios", "number"), ("costos", "number"), ("totales", "number"),
            ("precioventa", "number"), ("valortotal", "number"),
            ("cantidades", "integer"), ("activos", "boolean"),
        ],
    )
    def test_hint_tolera_plural_sufijo_numerico_y_raiz_pegada(self, name, expected):
        from app.services.schema_agent_service import _infer_column_type

        assert _infer_column_type(name, pd.Series(["x"])) == expected

    @pytest.mark.parametrize(
        "name", ["valoracion", "periodontitis", "totalidad", "diagnostico_principal", "preciosa"]
    )
    def test_hint_no_matchea_palabras_clinicas_que_solo_empiezan_igual(self, name):
        from app.services.schema_agent_service import _infer_column_type

        assert _infer_column_type(name, pd.Series(["gripe", "asma"])) == "text"

    @pytest.mark.parametrize(
        "series, expected",
        [
            (pd.Series([True, False, True]), "boolean"),
            (pd.Series(pd.to_datetime(["2024-01-01", "2024-02-01"])), "date"),
        ],
    )
    def test_bool_y_datetime_nativos_no_son_integer(self, series, expected):
        from app.services.schema_agent_service import _infer_column_type

        assert _infer_column_type("verificado_en", series) == expected


# ---------------------------------------------------------------------------
# analyze_csv
# ---------------------------------------------------------------------------

class TestAnalyzeCsv:
    def test_metadata_de_columnas(self):
        from app.services.schema_agent_service import analyze_csv

        df = pd.DataFrame({
            "Nombre Cliente": ["Ana", "Luis", None],
            "Edad": [30, 41, 25],
        })

        result = analyze_csv(df)

        assert result["row_count"] == 3
        assert result["column_count"] == 2
        nombre, edad = result["columns"]
        assert nombre["original_name"] == "Nombre Cliente"
        assert nombre["clean_name"] == "nombre_cliente"
        assert nombre["non_null_count"] == 2
        assert nombre["null_count"] == 1
        assert nombre["total_count"] == 3
        assert nombre["is_required"] is False
        assert nombre["unique_count"] == 2
        assert edad["is_required"] is True
        assert edad["inferred_type"] == "integer"

    def test_sample_values_maximo_cinco_y_como_texto(self):
        from app.services.schema_agent_service import analyze_csv

        df = pd.DataFrame({"x": list(range(20))})

        sample = analyze_csv(df)["columns"][0]["sample_values"]

        assert sample == ["0", "1", "2", "3", "4"]

    def test_encabezados_con_espacios_y_mayusculas(self):
        from app.services.schema_agent_service import analyze_csv

        df = pd.DataFrame({"  PRECIO Venta ": [1], "Ñandú": [2]})

        names = [c["clean_name"] for c in analyze_csv(df)["columns"]]

        assert names == ["precio_venta", "ñandú"]

    def test_dataframe_solo_encabezados(self):
        """CSV con encabezados y sin filas no debe romper el analisis."""
        from app.services.schema_agent_service import analyze_csv

        result = analyze_csv(pd.DataFrame(columns=["a", "b"]))

        assert result["row_count"] == 0
        assert result["column_count"] == 2
        assert all(c["inferred_type"] == "text" for c in result["columns"])

    def test_columna_totalmente_nula(self):
        from app.services.schema_agent_service import analyze_csv

        col = analyze_csv(pd.DataFrame({"x": [None, None]}))["columns"][0]

        assert col["non_null_count"] == 0
        assert col["null_count"] == 2
        assert col["unique_count"] == 0
        assert col["sample_values"] == []
        assert col["is_required"] is False

    def test_valores_json_serializables(self):
        """El router devuelve analyze_csv() via JSONResponse: no puede haber tipos numpy."""
        from app.services.schema_agent_service import analyze_csv

        df = pd.DataFrame({"a": [1, 2], "b": [1.5, None], "c": ["x", "y"]})

        json.dumps(analyze_csv(df))

    def test_encabezados_numericos(self):
        from app.services.schema_agent_service import analyze_csv

        result = analyze_csv(pd.DataFrame({2023: [1], 2024: [2]}))

        assert [c["clean_name"] for c in result["columns"]] == ["2023", "2024"]
        json.dumps(result)  # original_name tambien debe ser serializable (JSONResponse)

    def test_celdas_con_listas_y_dicts_no_rompen_el_conteo_de_unicos(self):
        from app.services.schema_agent_service import analyze_csv

        df = pd.DataFrame([
            {"id": 1, "tags": ["a", "b"], "meta": {"k": 1}},
            {"id": 2, "tags": ["a", "b"], "meta": {"k": 2}},
        ])

        cols = {c["clean_name"]: c for c in analyze_csv(df)["columns"]}

        assert cols["tags"]["unique_count"] == 1
        assert cols["meta"]["unique_count"] == 2


# ---------------------------------------------------------------------------
# _suggest_table_name
# ---------------------------------------------------------------------------

class TestSuggestTableName:
    def test_sin_coincidencias_usa_nombre_generico(self):
        from app.services.schema_agent_service import _suggest_table_name

        assert _suggest_table_name(["foo", "bar"]) == "datos_importados"

    def test_gana_la_categoria_con_mas_palabras_clave(self):
        from app.services.schema_agent_service import _suggest_table_name

        cols = ["Producto", "Precio Compra", "Precio Venta", "Stock"]

        assert _suggest_table_name(cols) == "productos"

    def test_empate_gana_la_primera_categoria_declarada(self):
        """'cliente' (clientes) y 'factura' (ventas/facturas) empatan en 1: gana la 1ra del dict."""
        from app.services.schema_agent_service import _suggest_table_name

        # 'ventas' se declara antes que 'facturas' y ambos puntuan 1 con 'factura'
        assert _suggest_table_name(["factura"]) == "ventas"

    def test_lista_vacia(self):
        from app.services.schema_agent_service import _suggest_table_name

        assert _suggest_table_name([]) == "datos_importados"

    def test_display_name_derivado_del_nombre(self):
        from app.services.schema_agent_service import analyze_csv

        result = analyze_csv(pd.DataFrame({"empleado": ["a"], "cargo": ["b"], "salario": [1]}))

        assert result["suggested_table_name"] == "empleados"
        assert result["suggested_display_name"] == "Empleados"


# ---------------------------------------------------------------------------
# find_matching_table
# ---------------------------------------------------------------------------

class TestFindMatchingTable:
    @pytest.mark.asyncio
    async def test_sin_tablas_retorna_none(self, org_dbs):
        from app.services.schema_agent_service import find_matching_table

        assert await find_matching_table(ORG_A, _cols("a", "b")) is None

    @pytest.mark.asyncio
    async def test_match_exacto_reporta_columnas(self, org_dbs):
        from app.services.schema_agent_service import find_matching_table

        tid = org_dbs.db(ORG_A).add_table("clientes", ["nombre", "ciudad", "edad"])

        result = await find_matching_table(ORG_A, _cols("nombre", "ciudad", "edad", "nueva"))

        assert result["table_id"] == str(tid)
        assert result["table_name"] == "clientes"
        assert set(result["matched_columns"]) == {"nombre", "ciudad", "edad"}
        assert result["missing_in_table"] == ["nueva"]
        assert result["extra_in_table"] == []
        assert result["columns_definition"][0]["name"] == "nombre"

    @pytest.mark.asyncio
    async def test_missing_y_extra_son_complementarios(self, org_dbs):
        from app.services.schema_agent_service import find_matching_table

        org_dbs.db(ORG_A).add_table("t", ["a", "b", "c"])

        result = await find_matching_table(ORG_A, _cols("b", "c", "d"))

        assert set(result["matched_columns"]) == {"b", "c"}
        assert set(result["missing_in_table"]) == {"d"}
        assert set(result["extra_in_table"]) == {"a"}

    @pytest.mark.asyncio
    async def test_un_solo_acierto_en_tabla_de_10_columnas_no_alcanza_umbral(self, org_dbs):
        """1 exacta: 1/10 + 0.1 de bonus fuzzy = 0.2 < 0.3 -> None."""
        from app.services.schema_agent_service import find_matching_table

        org_dbs.db(ORG_A).add_table("personas", TEN_COLS)

        assert await find_matching_table(ORG_A, _cols("nombre", "zzz1", "zzz2")) is None

    @pytest.mark.asyncio
    async def test_dos_aciertos_superan_umbral_de_candidato(self, org_dbs):
        """2 exactas: 0.2 + 0.2 = 0.4 >= 0.3 -> candidato."""
        from app.services.schema_agent_service import find_matching_table

        org_dbs.db(ORG_A).add_table("personas", TEN_COLS)

        result = await find_matching_table(ORG_A, _cols("nombre", "edad"))

        assert result is not None
        assert result["match_score"] == 0.4

    @pytest.mark.asyncio
    async def test_umbral_fuzzy_en_el_limite(self, org_dbs):
        """Nombres casi iguales (sim > 0.8) aportan 0.1 cada uno: 3 -> 0.3 acepta, 2 -> 0.2 rechaza."""
        from app.services.schema_agent_service import find_matching_table

        org_dbs.db(ORG_A).add_table("personas", TEN_COLS)

        tres = await find_matching_table(ORG_A, _cols("nombres", "apellidos", "ciudades"))
        dos = await find_matching_table(ORG_A, _cols("nombres", "apellidos"))

        assert tres is not None and tres["matched_columns"] == []
        assert dos is None

    @pytest.mark.asyncio
    async def test_similitud_exactamente_080_no_cuenta_como_fuzzy(self, org_dbs):
        """El bonus exige sim > 0.8 estricto: 3 pares con ratio == 0.8 no suman (con > 0.7 si sumarian 0.3)."""
        from difflib import SequenceMatcher
        from app.services.schema_agent_service import find_matching_table

        tabla = ["abcde", "fghij", "klmno", "pqrst", "uvwyz", "zyxwv", "qwert", "asdfg", "hjklm", "mnbvc"]
        csv = ["abcdx", "fghix", "klmnx"]
        assert all(SequenceMatcher(None, c, t).ratio() == 0.8 for c, t in zip(csv, tabla))
        org_dbs.db(ORG_A).add_table("t", tabla)

        assert await find_matching_table(ORG_A, _cols(*csv)) is None

    @pytest.mark.asyncio
    async def test_gana_la_tabla_con_mejor_score_sin_importar_el_orden(self, org_dbs):
        from app.services.schema_agent_service import find_matching_table

        db = org_dbs.db(ORG_A)
        db.add_table("amplia", TEN_COLS)                     # 3 aciertos / 10 cols -> 0.6
        mejor = db.add_table("compacta", ["nombre", "edad", "ciudad"])  # 3/3 -> 1.0+

        result = await find_matching_table(ORG_A, _cols("nombre", "edad", "ciudad"))

        assert result["table_id"] == str(mejor)

    @pytest.mark.asyncio
    async def test_empate_es_determinista_gana_la_primera_listada(self, org_dbs):
        """Dos tablas con el mismo score: `score > best_score` estricto deja la primera."""
        from app.services.schema_agent_service import find_matching_table

        db = org_dbs.db(ORG_A)
        primera = db.add_table("t_uno", ["a1", "b1"])
        db.add_table("t_dos", ["a1", "b1"])

        result = await find_matching_table(ORG_A, _cols("a1", "b1"))

        assert result["table_id"] == str(primera)

    @pytest.mark.asyncio
    async def test_columns_definition_como_lista_y_como_str(self, org_dbs):
        """asyncpg puede devolver jsonb como str o ya decodificado."""
        from app.services.schema_agent_service import find_matching_table

        db = org_dbs.db(ORG_A)
        tid = db.add_table("t", ["a", "b"])
        db.tables[tid]["columns_definition"] = [{"name": "a"}, {"name": "b"}]  # ya decodificado

        result = await find_matching_table(ORG_A, _cols("a", "b"))

        assert result["table_id"] == str(tid)

    @pytest.mark.asyncio
    async def test_tabla_sin_columnas_se_ignora(self, org_dbs):
        from app.services.schema_agent_service import find_matching_table

        db = org_dbs.db(ORG_A)
        db.add_table("vacia", [])

        assert await find_matching_table(ORG_A, _cols("a", "b")) is None

    @pytest.mark.asyncio
    async def test_csv_sin_columnas_no_hace_match(self, org_dbs):
        from app.services.schema_agent_service import find_matching_table

        org_dbs.db(ORG_A).add_table("t", ["a", "b"])

        assert await find_matching_table(ORG_A, []) is None

    @pytest.mark.asyncio
    async def test_no_ve_tablas_de_otra_organizacion(self, org_dbs):
        """Aislamiento multi-tenant: la tabla de ORG_B jamas es candidata para ORG_A."""
        from app.services.schema_agent_service import find_matching_table

        org_dbs.db(ORG_B).add_table("clientes", ["nombre", "ciudad", "edad"])
        org_dbs.db(ORG_A)  # ORG_A existe pero no tiene tablas

        assert await find_matching_table(ORG_A, _cols("nombre", "ciudad", "edad")) is None
        assert org_dbs.requested_org_ids == [ORG_A]

    @pytest.mark.asyncio
    async def test_match_score_no_excede_uno(self, org_dbs):
        from app.services.schema_agent_service import find_matching_table

        org_dbs.db(ORG_A).add_table("t", ["alfa", "beta", "gamma"])

        result = await find_matching_table(ORG_A, _cols("alfa", "beta", "gamma"))

        assert result["match_score"] <= 1.0

    @pytest.mark.asyncio
    async def test_tope_de_score_no_rompe_el_desempate(self, org_dbs):
        """La tabla exacta (3 cols) gana a la mas amplia (4 cols) aunque esta ultima se creo antes."""
        from app.services.schema_agent_service import find_matching_table

        db = org_dbs.db(ORG_A)
        db.add_table("amplia", ["nombre", "edad", "ciudad", "telefono"])
        db.add_table("exacta", ["nombre", "edad", "ciudad"])

        result = await find_matching_table(ORG_A, _cols("nombre", "edad", "ciudad"))

        assert result["table_name"] == "exacta"
        assert result["match_score"] <= 1.0


# ---------------------------------------------------------------------------
# create_table
# ---------------------------------------------------------------------------

class TestCreateTable:
    @pytest.mark.asyncio
    async def test_crea_tabla_con_cero_filas(self, org_dbs):
        from app.services.schema_agent_service import create_table

        cols = [{"name": "a", "type": "text"}]

        result = await create_table(ORG_A, "mi_tabla", "Mi Tabla", cols)

        db = org_dbs.db(ORG_A)
        assert uuid.UUID(result["table_id"]) in db.tables
        assert result["row_count"] == 0
        assert db.columns_of(uuid.UUID(result["table_id"])) == cols

    @pytest.mark.asyncio
    async def test_nombre_duplicado_devuelve_error_con_id_existente_sin_duplicar(self, org_dbs):
        from app.services.schema_agent_service import create_table

        primera = await create_table(ORG_A, "mi_tabla", "Mi Tabla", [{"name": "a"}])

        segunda = await create_table(ORG_A, "mi_tabla", "Otra", [{"name": "zzz"}])

        assert "ya existe" in segunda["error"]
        assert segunda["table_id"] == primera["table_id"]
        assert len(org_dbs.db(ORG_A).tables) == 1
        # la definicion original NO se pisa
        assert org_dbs.db(ORG_A).columns_of(uuid.UUID(primera["table_id"])) == [{"name": "a"}]

    @pytest.mark.asyncio
    async def test_mismo_nombre_en_orgs_distintas_no_colisiona(self, org_dbs):
        from app.services.schema_agent_service import create_table

        a = await create_table(ORG_A, "clientes", "Clientes", [])
        b = await create_table(ORG_B, "clientes", "Clientes", [])

        assert "error" not in a and "error" not in b
        assert len(org_dbs.db(ORG_A).tables) == 1
        assert len(org_dbs.db(ORG_B).tables) == 1


# ---------------------------------------------------------------------------
# modify_table
# ---------------------------------------------------------------------------

class TestModifyTable:
    @pytest.mark.asyncio
    async def test_agrega_solo_columnas_nuevas(self, org_dbs):
        from app.services.schema_agent_service import modify_table

        db = org_dbs.db(ORG_A)
        tid = db.add_table("t", ["a", "b"])

        result = await modify_table(
            ORG_A, str(tid), add_columns=[{"name": "b", "type": "number"}, {"name": "c", "type": "date"}],
        )

        names = [c["name"] for c in db.columns_of(tid)]
        assert names == ["a", "b", "c"]
        # la columna existente conserva su tipo original
        assert db.columns_of(tid)[1]["type"] == "text"
        assert [c["name"] for c in result["columns"]] == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_tabla_inexistente(self, org_dbs):
        from app.services.schema_agent_service import modify_table

        result = await modify_table(ORG_A, str(uuid.uuid4()), add_columns=[{"name": "x"}])

        assert result == {"error": "Tabla no encontrada"}

    @pytest.mark.asyncio
    async def test_tabla_de_otra_org_es_inexistente(self, org_dbs):
        from app.services.schema_agent_service import modify_table

        tid = org_dbs.db(ORG_B).add_table("t", ["a"])

        result = await modify_table(ORG_A, str(tid), add_columns=[{"name": "x"}])

        assert "error" in result
        assert [c["name"] for c in org_dbs.db(ORG_B).columns_of(tid)] == ["a"]

    @pytest.mark.asyncio
    async def test_cambia_solo_display_name_sin_tocar_columnas(self, org_dbs):
        from app.services.schema_agent_service import modify_table

        db = org_dbs.db(ORG_A)
        tid = db.add_table("t", ["a"], display_name="Viejo")

        result = await modify_table(ORG_A, str(tid), new_display_name="Nuevo")

        assert db.tables[tid]["display_name"] == "Nuevo"
        assert result["display_name"] == "Nuevo"
        assert [c["name"] for c in db.columns_of(tid)] == ["a"]

    @pytest.mark.asyncio
    async def test_sin_cambios_conserva_display_name(self, org_dbs):
        from app.services.schema_agent_service import modify_table

        db = org_dbs.db(ORG_A)
        tid = db.add_table("t", ["a"], display_name="Original")

        await modify_table(ORG_A, str(tid))

        assert db.tables[tid]["display_name"] == "Original"

    @pytest.mark.asyncio
    async def test_columns_added_cuenta_solo_las_realmente_agregadas(self, org_dbs):
        from app.services.schema_agent_service import modify_table

        tid = org_dbs.db(ORG_A).add_table("t", ["a", "b"])

        result = await modify_table(ORG_A, str(tid), add_columns=[{"name": "a"}, {"name": "b"}])

        assert result["columns_added"] == 0

    @pytest.mark.asyncio
    async def test_no_agrega_columnas_duplicadas_dentro_de_la_misma_llamada(self, org_dbs):
        from app.services.schema_agent_service import modify_table

        db = org_dbs.db(ORG_A)
        tid = db.add_table("t", ["a"])

        await modify_table(ORG_A, str(tid), add_columns=[{"name": "x"}, {"name": "x"}])

        names = [c["name"] for c in db.columns_of(tid)]
        assert names.count("x") == 1

    @pytest.mark.asyncio
    async def test_table_id_mal_formado_retorna_error(self, org_dbs):
        from app.services.schema_agent_service import modify_table

        result = await modify_table(ORG_A, "no-es-uuid", add_columns=[{"name": "x"}])

        assert "error" in result
