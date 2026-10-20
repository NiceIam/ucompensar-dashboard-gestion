"""Nombres legibles, titulos de graficos y unidad por rol — PI0320251.

Sin BD: se prueba el humanizador de encabezados, el vocabulario por rol y la unidad monetaria por ROL (un KPI de
cartera sin la palabra "valor" en el nombre debe salir en pesos).
"""

import pytest

from app.services import chart_specs as cs
from app.services import data_labels as labels
from app.services import data_query_engine as engine

K, N, D = engine.KIND_TEXT, engine.KIND_NUM, engine.KIND_DATE


class TestHumanizar:
    @pytest.mark.parametrize("raw, expected", [
        ("vr.total", "Valor total"),
        ("Vr.Total", "Valor total"),
        ("fec", "Fecha"),
        ("Fec", "Fecha"),
        ("p.unit", "Precio unitario"),
        ("P.Unit", "Precio unitario"),
        ("Cant", "Cantidad"),
        ("cant_vendida", "Cantidad vendida"),
        ("qty", "Cantidad"),
        ("Item", "Producto"),
        ("Sell Price", "Precio de venta"),
        ("Cost", "Costo"),
        ("metodoPago", "Método de pago"),
        ("precio_unitario", "Precio unitario"),
        ("cuánto_debe", "Cuánto debe"),
        ("¿Cuánto debe?", "Cuánto debe"),
        ("iva", "IVA"),
        ("fechaVenta", "Fecha venta"),
        ("categoria", "Categoría"),
        ("descripcion", "Descripción"),
        ("Nro.Factura", "Número factura"),
        ("C1", "C1"),
    ])
    def test_encabezados_crudos_a_nombres_legibles(self, raw, expected):
        assert labels.humanize(raw) == expected

    @pytest.mark.parametrize("raw", ["", None, "   ", "###", "_._"])
    def test_encabezados_vacios_no_rompen(self, raw):
        assert labels.humanize(raw) == "Columna"

    def test_un_encabezado_enorme_o_hostil_se_acota(self):
        out = labels.humanize("x" * 5000 + "<script>alert(1)</script>")
        assert len(out) <= 60

    def test_plural_de_la_primera_palabra(self):
        assert labels.plural("cliente") == "clientes"
        assert labels.plural("forma de pago") == "formas de pago"
        assert labels.plural("categoría") == "categorías"
        assert labels.plural("valor") == "valores"
        assert labels.plural("tipo de movimiento") == "tipos de movimiento"


def col(name, kind=K, role=None, label=None):
    return engine.Column(name, kind, None, role, label)


def table(kind=None, display="Ventas"):
    return engine.Table(id=1, name="t", display=display, rows=10, columns=(), sheet_kind=kind)


def key_of(column, bucket=None):
    return engine.Key(f"{bucket}({column.name})" if bucket else column.name, column, bucket)


def agg_of(fn, column=None):
    label = "count" if fn == "count" else f"{fn}({column.name})"
    return engine.Agg(label, fn, column, engine.KIND_NUM if fn in ("sum", "avg") else None)


class TestTitulos:
    def test_sin_rol_se_humaniza_el_encabezado(self):
        total = col("vr.total", N, label="Vr.Total")
        fecha = col("fec", D, label="Fec")
        assert cs.chart_title(key_of(fecha, "month"), agg_of("sum", total)) == "Valor total por mes"
        assert cs.chart_title(key_of(col("producto")), agg_of("sum", total)) == "Valor total por producto"

    def test_con_rol_usa_el_vocabulario_del_negocio(self):
        t = table("ventas")
        total = col("vr.total", N, "total", "Vr.Total")
        assert cs.chart_title(key_of(col("fec", D, "fecha"), "month"), agg_of("sum", total), t) == "Ventas por mes"
        assert cs.chart_title(key_of(col("mp", K, "metodo_pago")), agg_of("sum", total), t) == "Ventas por forma de pago"
        assert cs.chart_title(key_of(col("c", K, "cliente")), agg_of("avg", total), t) == "Venta promedio por cliente"

    def test_los_conteos_dicen_de_que(self):
        assert cs.chart_title(key_of(col("proveedor")), agg_of("count")) == "Número de registros por proveedor"
        assert cs.chart_title(key_of(col("p", K, "producto")), agg_of("count"), table("ventas")) == "Número de ventas por producto"

    def test_el_titulo_no_tiene_nombres_crudos(self):
        raw = col("vr.total", N)
        title = cs.chart_title(key_of(col("fec", D), "month"), agg_of("sum", raw))
        assert "vr." not in title and "fec" not in title.lower().split() and "Suma de" not in title

    def test_etiquetas_de_cifras(self):
        t = table("ventas")
        total = col("t", N, "total")
        assert labels.agg_title(agg_of("sum", total), t) == "Total vendido"
        assert labels.agg_title(agg_of("avg", total), t) == "Venta promedio"
        assert labels.agg_title(agg_of("count"), t) == "Registros de Ventas"
        assert labels.agg_title(agg_of("sum", col("vr.total", N)), None) == "Suma de valor total"
        deuda = col("cuánto_debe", N)
        assert labels.agg_title(agg_of("sum", deuda), None) == "Suma de cuánto debe"

    def test_encabezados_de_eje(self):
        assert labels.key_label(key_of(col("fec", D), "month")) == "Mes"
        assert labels.key_label(key_of(col("mp", K, "metodo_pago"))) == "Forma de pago"
        assert labels.key_label(key_of(col("fec", D))) == "Fecha"

    def test_titulo_del_dato_tocado(self):
        day = key_of(col("fecha", D, "fecha"), "day")
        assert labels.slice_title("Ventas", day, "2026-09-15") == "Ventas del 15 de septiembre de 2026"
        month = key_of(col("fecha", D, "fecha"), "month")
        assert labels.slice_title("Ventas", month, "2026-09") == "Ventas de septiembre de 2026"
        assert labels.slice_title("Ventas", key_of(col("fecha", D), "year"), "2026") == "Ventas de 2026"
        assert labels.slice_title("Ventas", key_of(col("fecha", D), "week"), "2026-09-14") == "Ventas de la semana del 14 de septiembre de 2026"
        prod = key_of(col("p", K, "producto"))
        assert labels.slice_title("Ventas", prod, "Cemento") == "Ventas de Cemento"
        assert labels.slice_title("Ventas", prod, None, empty=True) == "Ventas sin producto"
        assert labels.slice_title("Ventas", key_of(col("mp", K, "metodo_pago")), "efectivo") == "Ventas (pagadas con efectivo)"
        assert labels.slice_title("Ventas", key_of(col("sede")), "Norte") == "Ventas · Sede: Norte"


class TestUnidadPorRol:
    """La unidad ($) sale del ROL de la columna aunque su nombre sea raro; sin rol, del nombre (ampliado)."""

    @pytest.mark.parametrize("role", ["total", "precio_unitario", "costo_unitario", "valor", "precio_venta"])
    def test_los_roles_de_dinero_son_pesos_aunque_el_nombre_sea_raro(self, role):
        assert labels.unit_of(agg_of("sum", col("xq_9", N, role))) == "money"

    @pytest.mark.parametrize("role", ["cantidad", "stock"])
    def test_cantidad_y_existencias_nunca_son_pesos_ni_con_nombre_de_dinero(self, role):
        assert labels.unit_of(agg_of("sum", col("total_unidades", N, role))) == "number"

    def test_conteos_son_conteos(self):
        assert labels.unit_of(agg_of("count")) == "count"
        assert labels.unit_of(agg_of("count_distinct", col("cliente"))) == "count"

    @pytest.mark.parametrize("name", ["cuánto_debe", "cuanto_debe", "Vr.Total", "vlr_compra", "fiado", "cartera", "saldo"])
    def test_sin_rol_los_nombres_de_dinero_de_cartera_tambien_cuentan(self, name):
        assert labels.unit_of(agg_of("sum", col(name, N))) == "money"

    @pytest.mark.parametrize("name", ["cantidad", "stock", "unidades", "edad"])
    def test_sin_rol_lo_que_no_es_dinero_sigue_siendo_numero(self, name):
        assert labels.unit_of(agg_of("sum", col(name, N))) == "number"

    def test_el_encabezado_original_tambien_pesa(self):
        assert labels.unit_of(agg_of("sum", col("c3", N, None, "Cuánto debe"))) == "money"


class TestCatalogoConMetadata:
    def test_build_catalog_lee_rol_etiqueta_y_tipo_de_hoja_validados(self):
        import json

        cols = [
            {"name": "vr.total", "type": "number", "role": "total", "label": "Vr.Total",
             "sheet": {"kind": "ventas", "kind_confidence": 0.9, "mapping_source": "user", "signature": None}},
            {"name": "x", "type": "text", "role": "rol_inventado", "label": "X"},     # fuera de la lista blanca
            {"name": "y", "type": "text", "role": "otro"},
        ]
        catalog = engine.build_catalog([{"id": 1, "table_name": "t", "display_name": "T", "row_count": 3,
                                         "columns_definition": json.dumps(cols)}])
        t = catalog["t"]
        assert t.sheet_kind == "ventas"
        assert [(c.name, c.role, c.label) for c in t.columns] == [
            ("vr.total", "total", "Vr.Total"), ("x", None, "X"), ("y", None, None)]

    def test_una_tabla_antigua_sin_metadata_se_comporta_como_siempre(self):
        catalog = engine.build_catalog([{"id": 1, "table_name": "t", "display_name": "T", "row_count": 3,
                                         "columns_definition": [{"name": "a", "type": "number"}]}])
        t = catalog["t"]
        assert t.sheet_kind is None and t.columns[0].role is None and t.columns[0].label is None
