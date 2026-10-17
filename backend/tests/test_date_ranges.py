"""Rango de fechas por columna (columns_definition[].range) — PI0320251.

El rango se calcula UNA vez, al cargar datos (load_csv_to_table / smart_upload / modify_table), con el motor de
consultas del chat (data_query_engine.date_ranges): el mismo parseo de fechas que usan los filtros, asi el
catalogo del prompt nunca contradice lo que el motor devuelve. Tambien se prueba el mantenimiento
backfill_date_ranges para tablas cargadas antes de que existiera.

Aqui la BD se emula (tests/fake_org_db.py) y el motor se reemplaza por el oraculo en pandas
(tests/query_oracle.py). El mismo escenario contra Postgres REAL esta en tests/test_date_ranges_pg.py.
Gemini no participa.
"""

import json
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from app.services import data_query_engine as engine
from app.services import schema_agent_service as svc
from tests.fake_org_db import FakeOrgDBs
from tests.query_oracle import fake_run_plan_on, fake_run_plans

ORG_A = "550e8400-e29b-41d4-a716-446655440000"
ORG_B = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
TODAY = date(2026, 10, 16)       # ventana de años de 2 digitos: 00-31 -> 20xx, 32-99 -> 19xx
UPDATE_COLUMNS = "update org_data_tables set columns_definition = $1::jsonb where id = $2"


@pytest.fixture
def org_dbs():
    dbs = FakeOrgDBs()
    with patch("app.services.schema_agent_service.get_org_pool", dbs.get_org_pool), patch(
        "app.services.data_query_engine.run_plan_on", fake_run_plan_on()
    ), patch("app.services.data_query_engine.today", return_value=TODAY):
        yield dbs


def new_table(dbs, rows=None, name="ventas", column_ranges=None):
    return dbs.db(ORG_A).add_table(
        name, ["fecha", "producto", "total"], rows or [], column_types={"fecha": "date", "total": "number"},
        column_ranges=column_ranges,
    )


def column(dbs, tid, name="fecha") -> dict:
    return next(c for c in dbs.db(ORG_A).columns_of(tid) if c["name"] == name)


async def load(dbs, tid, fechas):
    df = pd.DataFrame({"fecha": fechas, "producto": ["x"] * len(fechas), "total": list(range(len(fechas)))})
    return await svc.load_csv_to_table(df, ORG_A, str(tid))


class TestRangoAlCargar:
    async def test_fechas_iso(self, org_dbs):
        tid = new_table(org_dbs)

        await load(org_dbs, tid, ["2026-03-15", "2026-01-05", "2026-06-28"])

        assert column(org_dbs, tid)["range"] == ["2026-01-05", "2026-06-28"]

    async def test_conserva_el_resto_de_la_definicion_y_no_toca_otras_columnas(self, org_dbs):
        tid = new_table(org_dbs)

        await load(org_dbs, tid, ["2026-03-15"])

        cols = org_dbs.db(ORG_A).columns_of(tid)
        assert cols == [
            {"name": "fecha", "type": "date", "range": ["2026-03-15", "2026-03-15"]},
            {"name": "producto", "type": "text"},
            {"name": "total", "type": "number"},
        ]

    async def test_dia_mes_y_año_de_2_digitos_con_la_misma_ventana_del_motor(self, org_dbs):
        tid = new_table(org_dbs)

        await load(org_dbs, tid, ["15/03/26", "01/12/31", "05/06/55", "03/04/2024"])

        # 55 -> 1955 y 31 -> 2031 (ventana de 2026), 03/04/2024 es DIA/MES: 3 de abril
        assert column(org_dbs, tid)["range"] == ["1955-06-05", "2031-12-01"]

    async def test_año_y_mes(self, org_dbs):
        tid = new_table(org_dbs)

        await load(org_dbs, tid, ["2026-11", "2026-02", "2026-7"])

        assert column(org_dbs, tid)["range"] == ["2026-02-01", "2026-11-01"]

    async def test_celdas_ilegibles_se_ignoran(self, org_dbs):
        tid = new_table(org_dbs)

        await load(org_dbs, tid, ["no es fecha", "2026-02-30", "2026-04-10", "15-mar-2026", "13/13/2026"])

        assert column(org_dbs, tid)["range"] == ["2026-04-10", "2026-04-10"]

    async def test_sin_fechas_legibles_no_hay_rango_y_la_carga_funciona(self, org_dbs):
        tid = new_table(org_dbs)

        result = await load(org_dbs, tid, ["mañana", "n/a", "2026-02-30"])

        assert result["rows_inserted"] == 3
        assert "range" not in column(org_dbs, tid)

    async def test_columna_de_fecha_sin_valores_en_el_archivo(self, org_dbs):
        tid = new_table(org_dbs)
        df = pd.DataFrame({"producto": ["a", "b"]})

        result = await svc.load_csv_to_table(df, ORG_A, str(tid))

        assert result["rows_inserted"] == 2
        assert "range" not in column(org_dbs, tid)

    async def test_tabla_sin_columnas_de_fecha_no_calcula_nada(self, org_dbs):
        tid = org_dbs.db(ORG_A).add_table("clientes", ["nombre"], [])
        with patch("app.services.data_query_engine.run_plan_on") as run:
            await svc.load_csv_to_table(pd.DataFrame({"nombre": ["Ana"]}), ORG_A, str(tid))

        run.assert_not_called()
        assert org_dbs.db(ORG_A).columns_of(tid) == [{"name": "nombre", "type": "text"}]

    async def test_varias_columnas_de_fecha_cada_una_con_su_rango(self, org_dbs):
        db = org_dbs.db(ORG_A)
        tid = db.add_table("citas", ["creada", "vence", "nota"], [], column_types={"creada": "date", "vence": "datetime"})
        df = pd.DataFrame({
            "creada": ["2026-01-02", "2026-05-06"], "vence": ["01/02/2027", "03/04/2028"], "nota": ["a", "b"],
        })

        await svc.load_csv_to_table(df, ORG_A, str(tid))

        assert column(org_dbs, tid, "creada")["range"] == ["2026-01-02", "2026-05-06"]
        assert column(org_dbs, tid, "vence")["range"] == ["2027-02-01", "2028-04-03"]
        assert "range" not in column(org_dbs, tid, "nota")

    async def test_un_tipo_que_no_es_fecha_nunca_lleva_rango_aunque_parezca_fecha(self, org_dbs):
        tid = org_dbs.db(ORG_A).add_table("t", ["cuando"], [])     # declarada como texto

        await svc.load_csv_to_table(pd.DataFrame({"cuando": ["2026-01-02"]}), ORG_A, str(tid))

        assert "range" not in column(org_dbs, tid, "cuando")

    async def test_el_rango_y_las_filas_se_guardan_juntos(self, org_dbs):
        """Misma transaccion: si la carga falla despues del rango, ni filas ni rango quedan."""
        db = org_dbs.db(ORG_A)
        tid = new_table(org_dbs)
        db.fail_when = lambda q, args: q == UPDATE_COLUMNS

        with pytest.raises(Exception):
            await load(org_dbs, tid, ["2026-03-15"])

        assert db.rows_of(tid) == [] and db.tables[tid]["row_count"] == 0
        assert "range" not in column(org_dbs, tid)


class TestRangoAlAgregarFilas:
    async def test_carga_posterior_extiende_minimo_y_maximo(self, org_dbs):
        tid = new_table(org_dbs)
        await load(org_dbs, tid, ["2026-03-15", "2026-04-01"])

        await load(org_dbs, tid, ["2026-01-05", "2026-02-01"])
        assert column(org_dbs, tid)["range"] == ["2026-01-05", "2026-04-01"]

        await load(org_dbs, tid, ["2026-12-31"])
        assert column(org_dbs, tid)["range"] == ["2026-01-05", "2026-12-31"]

    async def test_carga_dentro_del_rango_no_reescribe_la_definicion(self, org_dbs):
        tid = new_table(org_dbs)
        await load(org_dbs, tid, ["2026-01-05", "2026-06-28"])
        db = org_dbs.db(ORG_A)
        before = sum(1 for q in db.sql_log if q == UPDATE_COLUMNS)

        await load(org_dbs, tid, ["2026-03-01"])

        assert before == 1 and sum(1 for q in db.sql_log if q == UPDATE_COLUMNS) == 1
        assert column(org_dbs, tid)["range"] == ["2026-01-05", "2026-06-28"]

    async def test_tabla_vieja_sin_rango_lo_calcula_sobre_TODAS_las_filas_no_solo_las_nuevas(self, org_dbs):
        tid = new_table(org_dbs, rows=[
            {"fecha": "2024-01-10", "producto": "viejo", "total": 1},
            {"fecha": "2025-07-01", "producto": "viejo", "total": 2},
        ])
        assert "range" not in column(org_dbs, tid)

        await load(org_dbs, tid, ["2026-03-15"])

        assert column(org_dbs, tid)["range"] == ["2024-01-10", "2026-03-15"]

    async def test_smart_upload_a_tabla_nueva_y_luego_a_la_existente(self, org_dbs):
        first = pd.DataFrame({"fecha": ["2026-03-15", "2026-03-20"], "producto": ["a", "b"], "total": [1, 2]})
        second = pd.DataFrame({"fecha": ["2025-12-01"], "producto": ["c"], "total": [3]})

        created = await svc.smart_upload(first, ORG_A, "ventas.csv")
        tid = org_dbs.db(ORG_A).table_by_name(created["table_name"])["id"]
        assert column(org_dbs, tid)["range"] == ["2026-03-15", "2026-03-20"]

        again = await svc.smart_upload(second, ORG_A, "ventas2.csv")

        assert again["status"] == "loaded_to_existing" and again["table_id"] == str(tid)
        assert column(org_dbs, tid)["range"] == ["2025-12-01", "2026-03-20"]

    async def test_smart_upload_declara_columnas_nuevas_de_fecha_y_calcula_su_rango(self, org_dbs):
        db = org_dbs.db(ORG_A)
        tid = db.add_table("ventas", ["producto", "total"], [{"producto": "a", "total": 1}],
                           column_types={"total": "number"})
        df = pd.DataFrame({
            "producto": ["a", "b"], "total": [1, 2], "fecha": ["2026-02-01", "2026-09-30"],
        })

        result = await svc.smart_upload(df, ORG_A, "ventas.csv")

        assert result["table_id"] == str(tid)
        assert column(org_dbs, tid)["range"] == ["2026-02-01", "2026-09-30"]

    async def test_modify_table_con_columna_de_fecha_que_ya_tiene_datos_anota_el_rango(self, org_dbs):
        db = org_dbs.db(ORG_A)
        tid = db.add_table("citas", ["nota"], [
            {"nota": "a", "cuando": "2026-05-01"}, {"nota": "b", "cuando": "2026-08-09"}, {"nota": "c"},
        ])

        result = await svc.modify_table(ORG_A, str(tid), add_columns=[{"name": "cuando", "type": "date"}])

        assert result["columns_added"] == 1
        assert column(org_dbs, tid, "cuando")["range"] == ["2026-05-01", "2026-08-09"]
        assert {"name": "cuando", "type": "date", "range": ["2026-05-01", "2026-08-09"]} in result["columns"]

    async def test_modify_table_sin_columnas_de_fecha_nuevas_no_consulta_el_motor(self, org_dbs):
        tid = new_table(org_dbs, column_ranges={"fecha": ["2026-01-01", "2026-02-02"]})
        with patch("app.services.data_query_engine.run_plan_on") as run:
            await svc.modify_table(ORG_A, str(tid), add_columns=[{"name": "nota", "type": "text"}])

        run.assert_not_called()
        assert column(org_dbs, tid)["range"] == ["2026-01-01", "2026-02-02"]      # se conserva


class TestUnaFallaDelRangoNoTumbaLaCarga:
    @pytest.mark.parametrize("error", [RuntimeError("boom con CELDA_SECRETA"), AssertionError("sql raro")])
    async def test_la_carga_sigue_sin_rango(self, org_dbs, error, caplog):
        tid = new_table(org_dbs)

        async def broken(conn, plan):
            raise error

        with patch("app.services.data_query_engine.run_plan_on", broken):
            result = await load(org_dbs, tid, ["2026-03-15", "2026-04-01"])

        assert result["rows_inserted"] == 2 and result["total_rows"] == 2
        assert org_dbs.db(ORG_A).tables[tid]["row_count"] == 2
        assert "range" not in column(org_dbs, tid)
        assert "CELDA_SECRETA" not in caplog.text          # el detalle puede citar datos: solo el tipo de error

    async def test_una_definicion_corrupta_no_rompe_la_carga(self, org_dbs):
        tid = new_table(org_dbs)
        org_dbs.db(ORG_A).tables[tid]["columns_definition"] = "esto no es json"

        result = await load(org_dbs, tid, ["2026-03-15"])

        assert result["rows_inserted"] == 1

    async def test_rango_guardado_de_forma_invalida_se_reemplaza_al_cargar(self, org_dbs):
        tid = new_table(org_dbs, column_ranges={"fecha": "basura"})

        await load(org_dbs, tid, ["2026-03-15"])

        assert column(org_dbs, tid)["range"] == ["2026-03-15", "2026-03-15"]


class TestCoincideConLoQueElMotorFiltra:
    """El rango sale del motor: un filtro >= min y <= max devuelve TODAS las filas con fecha legible."""

    MIXED = ["2026-01-05", "15/03/26", "01/12/31", "05/06/55", "2026-11", "20260704", "5-1-2026", "2026/2/3",
             "2026-03-15 10:00:00", "no es fecha", "2026-02-30", "13/13/2026", "", "03/04/2024"]

    async def test_filtro_entre_min_y_max_devuelve_todas_las_filas_legibles(self, org_dbs):
        tid = new_table(org_dbs)
        await load(org_dbs, tid, self.MIXED)
        lo, hi = column(org_dbs, tid)["range"]
        db = org_dbs.db(ORG_A)
        catalog = engine.build_catalog(
            [{"id": tid, "table_name": "ventas", "display_name": "Ventas", "row_count": len(self.MIXED),
              "columns_definition": db.tables[tid]["columns_definition"]}]
        )
        table = catalog["ventas"]

        readable = engine_readable_count(self.MIXED)
        assert (lo, hi) == ("1955-06-05", "2031-12-01")
        assert await async_count(db, table, [["fecha", ">=", lo], ["fecha", "<=", hi]]) == readable
        # y el rango es justo: un dia fuera de el no incluye nada mas
        assert await async_count(db, table, [["fecha", "<", lo]]) == 0
        assert await async_count(db, table, [["fecha", ">", hi]]) == 0


def engine_readable_count(values) -> int:
    from tests import query_oracle

    query_oracle._YEAR[0] = TODAY.year
    return sum(1 for v in values if query_oracle.date_of(v) is not None)


async def async_count(db, table, filters) -> int:
    class Pool:
        pass

    pool = Pool()
    pool.db = db
    plan = engine.build_plan(table, filters=filters, aggregates=["count"])
    (result,) = await fake_run_plans()(pool, [plan])
    return result.rows[0][0]


class TestBackfill:
    @staticmethod
    def seed(dbs):
        """Dos tablas viejas con fechas (sin rango), una vacia, una sin fechas y una que ya trae rango."""
        db = dbs.db(ORG_A)
        ventas = db.add_table("ventas", ["fecha", "total"], [
            {"fecha": "2026-01-05", "total": 1}, {"fecha": "15/03/26", "total": 2}, {"fecha": "n/a", "total": 3},
        ], column_types={"fecha": "date", "total": "number"})
        db.add_table("vacia", ["fecha"], [], column_types={"fecha": "date"})
        db.add_table("clientes", ["nombre"], [{"nombre": "Ana"}])
        con_rango = db.add_table(
            "citas", ["cuando"], [{"cuando": "2026-02-02"}], column_types={"cuando": "date"},
            column_ranges={"cuando": ["2020-01-01", "2020-12-31"]},       # desactualizado a proposito
        )
        return ventas, con_rango

    async def test_dry_run_calcula_pero_no_escribe_nada(self, org_dbs):
        ventas, _ = self.seed(org_dbs)
        db = org_dbs.db(ORG_A)
        before = json.dumps({str(k): v for k, v in db.tables.items()}, default=str)

        report = await svc.backfill_date_ranges(ORG_A)

        assert report == [{
            "table": "ventas", "rows": 3, "ranges": {"fecha": ["2026-01-05", "2026-03-15"]},
            "changed": True, "applied": False,
        }]
        assert json.dumps({str(k): v for k, v in db.tables.items()}, default=str) == before
        assert not any(q == UPDATE_COLUMNS for q in db.sql_log)

    async def test_aplicar_escribe_solo_lo_que_falta(self, org_dbs):
        ventas, con_rango = self.seed(org_dbs)

        report = await svc.backfill_date_ranges(ORG_A, dry_run=False)

        assert [r["table"] for r in report] == ["ventas"] and report[0]["applied"] is True
        assert column(org_dbs, ventas)["range"] == ["2026-01-05", "2026-03-15"]
        assert column(org_dbs, con_rango, "cuando")["range"] == ["2020-01-01", "2020-12-31"]   # no se toca
        assert await svc.backfill_date_ranges(ORG_A, dry_run=False) == []                      # idempotente

    async def test_refresh_recalcula_tambien_las_que_ya_tenian_rango(self, org_dbs):
        _, con_rango = self.seed(org_dbs)

        report = await svc.backfill_date_ranges(ORG_A, dry_run=False, refresh=True)

        assert {r["table"] for r in report} == {"ventas", "citas"}
        assert column(org_dbs, con_rango, "cuando")["range"] == ["2026-02-02", "2026-02-02"]

    async def test_una_org_no_toca_a_la_otra(self, org_dbs):
        self.seed(org_dbs)
        other = org_dbs.db(ORG_B)
        tid = other.add_table("ventas", ["fecha"], [{"fecha": "2026-01-01"}], column_types={"fecha": "date"})

        await svc.backfill_date_ranges(ORG_A, dry_run=False)

        assert "range" not in other.columns_of(tid)[0]
        assert org_dbs.requested_org_ids == [ORG_A]

    async def test_acepta_un_pool_ya_abierto(self, org_dbs):
        ventas, _ = self.seed(org_dbs)
        pool = await org_dbs.get_org_pool(ORG_A)

        await svc.backfill_date_ranges("no se usa", dry_run=False, pool=pool)

        assert column(org_dbs, ventas)["range"] == ["2026-01-05", "2026-03-15"]
