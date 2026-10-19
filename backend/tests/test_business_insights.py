"""Hallazgos de negocio ("Esta semana en tu negocio") — PI0320251.

Sin Gemini y sin red. Cada prueba corre en dos backends (ver tests/insights_support.py):
- oraculo: BD emulada + motor reemplazado por el oraculo pandas del motor (siempre).
- postgres: Postgres real desechable (solo con CHAT_TOOLS_TEST_PG_PORT; si no, se omite).

Los valores esperados de los datos de ejemplo (test-data/ferreteria) y de los casos sinteticos son LITERALES
escritos a mano: los de la ferreteria salieron de dos calculos independientes (pandas y csv + Fraction) y los
sinteticos se resolvieron a mano (ver el comentario de cada caso). tests/insights_oracle.py cubre ademas datos
aleatorios y sucios por comparacion.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.services import business_insights_service as svc
from tests.insights_support import (
    NOW, ORG_A, ORG_B, PROD_COLS, SALE_COLS, item, make_backend, metrics, missing, prods, read_csv, sales,
    stringify,
)

ALL_RECIPES = ["capital_inventario", "productos_estrella", "reposicion", "clientes_concentracion",
               "sin_movimiento", "margen_bajo"]


@pytest.fixture(params=["oraculo", "postgres"])
async def backend(request):
    be, patches = await make_backend(request.param)
    for p in patches:
        p.start()
    try:
        yield be
    finally:
        for p in patches:
            p.stop()
        if request.param == "postgres":
            await be.close()


async def run(now=NOW, org=ORG_A):
    return await svc.get_business_insights(org, now=now)


async def load(backend, productos=None, ventas=None, org=ORG_A, pname="productos", vname="ventas",
               pcols=None, vcols=None):
    if productos is not None:
        await backend.add_table(pname, pcols or PROD_COLS, productos, display=pname.title(), org=org)
    if ventas is not None:
        await backend.add_table(vname, vcols or SALE_COLS, ventas, display=vname.title(), org=org)


async def load_ferreteria(backend, as_text=False, org=ORG_A):
    cols, rows = read_csv("productos", as_text)
    await backend.add_table("productos", {"nombre": "text", "categoria": "text", "precio_compra": "number",
                                          "precio_venta": "number", "stock": "integer", "proveedor": "text",
                                          "codigo": "text"}, rows, display="Productos", org=org)
    cols, rows = read_csv("ventas", as_text)
    await backend.add_table("ventas", {"fecha": "date", "producto": "text", "cantidad": "integer",
                                       "precio_unitario": "number", "total": "number", "cliente": "text",
                                       "metodo_pago": "text"}, rows, display="Ventas", org=org)
    cols, rows = read_csv("proveedores", as_text)
    await backend.add_table("proveedores", {c: "text" for c in cols}, rows, display="Proveedores", org=org)
    cols, rows = read_csv("inventario_movimientos", as_text)
    await backend.add_table("inventario_movimientos", {"fecha": "date", "producto": "text",
                                                       "tipo_movimiento": "text", "cantidad": "integer",
                                                       "motivo": "text"}, rows, display="Movimientos", org=org)


# ===========================================================================
# Formato es-CO y normalizacion
# ===========================================================================

class TestFormato:
    @pytest.mark.parametrize("value,text", [
        (47_620_000, "$47,6 M"), (360_000, "$360.000"), (1_234_000_000, "$1,2 mil millones"),
        (10_000_000, "$10 M"), (0, "$0"), (-1_500_000, "-$1,5 M"), (2_500_000_000_000, "$2,5 billones"),
        (999_960, "$999.960"), (999_999.6, "$1 M"), (999_960_000_000, "$1 billón"), (1_000_000, "$1 M"),
        (12_345, "$12.345"), (10_234_700, "$10,2 M"), (99_950_000, "$100 M"), (0.4, "$0"),
        (10**21, "$1.000.000.000 billones"),
    ])
    def test_dinero(self, value, text):
        assert svc.fmt_money(value) == text

    @pytest.mark.parametrize("ratio,text", [
        (0.36298, "36 %"), (0.045, "4,5 %"), (0.0996, "10 %"), (1.04, "104 %"), (0.1, "10 %"), (0, "0 %"),
        (0.0, "0 %"), (0.995, "100 %"),
    ])
    def test_porcentaje(self, ratio, text):
        assert svc.fmt_percent(ratio) == text

    def test_fechas_y_rangos(self):
        from datetime import date
        assert svc.fmt_date(date(2025, 7, 2)) == "2 de julio de 2025"
        assert svc.fmt_range(date(2025, 7, 2), date(2025, 10, 8)) == "entre el 2 de julio y el 8 de octubre de 2025"
        assert svc.fmt_range(date(2024, 12, 30), date(2025, 1, 3)) == (
            "entre el 30 de diciembre de 2024 y el 3 de enero de 2025")
        assert svc.fmt_range(date(2025, 7, 2), date(2025, 7, 2)) == "el 2 de julio de 2025"

    def test_clave_de_producto(self):
        assert svc.product_key("  Taladro   BOSCH  Áé ñ ") == "taladro bosch ae n"
        assert svc.product_key("Taládro Bosch") == svc.product_key("TALADRO bosch")
        assert svc.product_key("A B") == "a b"

    def test_meses_en_palabras(self):
        from decimal import Decimal as D
        assert svc.months_phrase(D("0.5")) == "menos de un mes"
        assert svc.months_phrase(D("3.1")) == "unos 3 meses"
        assert svc.months_phrase(D("12")) == "más de un año"
        assert svc.months_phrase(D("21")) == "más de un año"
        assert svc.months_phrase(D("25")) == "más de 2 años"


# ===========================================================================
# Deteccion de roles por columnas
# ===========================================================================

def _catalog(**tables):
    """{nombre: [columnas]} -> catalogo del motor (filas = 1 para que cuenten)."""
    import json
    import uuid
    from app.services import data_query_engine as engine
    records = [{"id": uuid.uuid4(), "table_name": n, "display_name": n, "row_count": 1,
                "columns_definition": json.dumps([{"name": c, "type": "text"} for c in cols])}
               for n, cols in tables.items()]
    return engine.build_catalog(records)


class TestRoles:
    @pytest.mark.parametrize("headers,expected", [
        (["Producto", "Existencias", "Costo Unitario", "Precio Venta"], {"nombre": "Producto", "stock": "Existencias",
                                                                          "costo": "Costo Unitario"}),
        (["DESCRIPCIÓN", "Precio de Compra", "Cantidad Disponible"],
         {"nombre": "DESCRIPCIÓN", "costo": "Precio de Compra", "stock": "Cantidad Disponible"}),
        (["articulo", "vr costo", "exist"], {"nombre": "articulo", "costo": "vr costo", "stock": "exist"}),
        (["Nombre_Producto", "costo-promedio", "STOCK"], {"nombre": "Nombre_Producto", "costo": "costo-promedio",
                                                           "stock": "STOCK"}),
        (["nombre", "precio_compra", "precio_venta", "stock", "codigo"],
         {"nombre": "nombre", "costo": "precio_compra", "stock": "stock", "precio_venta": "precio_venta"}),
        (["Referencia", "Costo (COP)", "Inventario"], {"nombre": "Referencia", "costo": "Costo (COP)",
                                                       "stock": "Inventario"}),
    ])
    def test_hoja_de_productos_con_nombres_variados(self, headers, expected):
        roles, alts, _ = svc.detect_roles(_catalog(hoja1=headers))
        assert "productos" in roles and "ventas" not in roles
        assert {f: c.name for f, c in roles["productos"].fields.items() if f in expected} == expected

    @pytest.mark.parametrize("headers,expected", [
        (["Fecha de Venta", "Artículo", "Unidades", "Valor Total", "Cliente"],
         {"fecha": "Fecha de Venta", "producto": "Artículo", "cantidad": "Unidades", "total": "Valor Total",
          "cliente": "Cliente"}),
        (["FECHA", "PRODUCTO", "CANTIDAD", "PRECIO UNITARIO"],
         {"fecha": "FECHA", "producto": "PRODUCTO", "cantidad": "CANTIDAD", "precio_unitario": "PRECIO UNITARIO"}),
        (["fec", "descripcion", "cant", "vlr unit", "total"],
         {"fecha": "fec", "producto": "descripcion", "cantidad": "cant", "precio_unitario": "vlr unit",
          "total": "total"}),
        (["fecha_factura", "nombre_producto", "cantidad_vendida", "importe", "razon_social"],
         {"fecha": "fecha_factura", "producto": "nombre_producto", "cantidad": "cantidad_vendida",
          "total": "importe", "cliente": "razon_social"}),
    ])
    def test_hoja_de_ventas_con_nombres_variados(self, headers, expected):
        roles, _alts, _ = svc.detect_roles(_catalog(x=headers))
        assert "ventas" in roles and "productos" not in roles
        assert {f: c.name for f, c in roles["ventas"].fields.items()} == expected

    def test_el_nombre_de_la_tabla_no_importa(self):
        roles, _a, _ = svc.detect_roles(_catalog(
            hoja1=["nombre", "costo", "stock"], datos_raros=["fecha", "producto", "cantidad", "total"]))
        assert roles["productos"].table.name == "hoja1" and roles["ventas"].table.name == "datos_raros"
        # una tabla que se LLAMA "ventas" pero no tiene columnas de ventas no es ventas
        roles, _a, _ = svc.detect_roles(_catalog(ventas=["a", "b", "c"], productos=["x", "y"]))
        assert roles == {}

    def test_movimientos_de_inventario_no_se_confunden_con_productos_ni_ventas(self):
        roles, _a, _ = svc.detect_roles(_catalog(
            inventario_movimientos=["fecha", "producto", "tipo_movimiento", "cantidad", "motivo"]))
        assert roles == {}

    def test_una_columna_sirve_a_un_solo_campo(self):
        roles, _a, _ = svc.detect_roles(_catalog(t=["fecha", "producto", "cantidad", "precio"]))
        # "precio" sirve como precio unitario; no hay total: aun asi califica como ventas
        assert roles["ventas"].fields["precio_unitario"].name == "precio"
        assert "total" not in roles["ventas"].fields

    def test_ambiguedad_elige_la_de_mayor_puntaje_y_la_senala(self):
        roles, _a, _ = svc.detect_roles(_catalog(p=["nombre", "costo", "stock", "existencias"]))
        fields = roles["productos"].fields
        assert fields["stock"].name == "stock"      # empate: la primera
        assert roles["productos"].ambiguous["stock"] == ["stock", "existencias"]

    def test_dos_hojas_de_ventas_se_usa_una_y_se_deja_nota(self):
        cols = ["fecha", "producto", "cantidad", "total"]
        catalog = _catalog(ventas_2024=cols, ventas=cols + ["cliente"])
        roles, alts, _ = svc.detect_roles(catalog)
        assert roles["ventas"].table.name == "ventas"       # mas columnas reconocidas
        assert [m.table.name for m in alts["ventas"]] == ["ventas_2024"]

    def test_hoja_de_cartera_se_detecta(self):
        _r, _a, has = svc.detect_roles(_catalog(cobrar=["cliente", "saldo", "fecha vencimiento"]))
        assert has
        _r, _a, has = svc.detect_roles(_catalog(x=["cliente", "total"]))
        assert not has

    @pytest.mark.parametrize("headers", [
        ["Sku", "Marca", "Color"],                           # sin nada que reconocer
        ["price", "quantity", "customer", "date", "name"],   # encabezados en ingles
        ["C1", "C2", "C3", "C4"],
        ["Col A", "Col B", "Col C"],
    ])
    def test_lo_que_no_entiende_no_genera_rol(self, headers):
        roles, _a, _ = svc.detect_roles(_catalog(t=headers))
        assert roles == {}


# ===========================================================================
# Datos de ejemplo: ferreteria (valores literales calculados de forma independiente)
# ===========================================================================

class TestFerreteria:
    @pytest.fixture(params=[False, True], ids=["numeros", "texto"])
    async def result(self, backend, request):
        await load_ferreteria(backend, as_text=request.param)
        return await run()

    def test_forma_del_contrato(self, result):
        assert set(result) == {"generated_at", "recipe_pack", "period", "items", "missing", "summary_text"}
        assert result["generated_at"] == "2025-10-20T15:00:00Z"
        assert result["recipe_pack"] == "ferreteria"
        assert result["period"] == {"from": "2025-07-02", "to": "2025-10-08", "days": 99}
        # severidad, luego lo accionable (con action) y al final los "todo bien"; a igual cosa, por impacto
        assert [(i["id"], i["severity"], i["action"] is not None) for i in result["items"]] == [
            ("capital_inventario", "important", True), ("sin_movimiento", "info", True),
            ("clientes_concentracion", "info", True), ("productos_estrella", "info", True),
            ("reposicion", "info", False), ("margen_bajo", "info", False)]
        for it in result["items"]:
            assert set(it) == {"id", "kind", "severity", "title", "sentence", "metrics", "action", "ask", "how"}
            assert it["kind"] in ("money", "risk", "opportunity", "info")
            assert it["severity"] in ("info", "attention", "important")
            assert len(it["title"]) <= 60
            assert set(it["how"]) == {"steps", "tables", "rows_used", "notes"}
            assert it["how"]["steps"] and it["how"]["tables"]
            assert all(m["unit"] in ("money", "count", "percent", "days", "months", "text") for m in it["metrics"])
        assert [m["id"] for m in result["missing"]] == ["cartera"]
        assert result["missing"][0]["needs"] == (
            "Una hoja con cliente, valor y fecha de vencimiento de cada cuenta por cobrar.")

    def test_capital_inventario(self, result):
        it = item(result, "capital_inventario")
        assert it["severity"] == "important" and it["kind"] == "money"
        assert it["title"] == "Tienes $47,6 M en mercancía"
        assert it["sentence"] == (
            "Es lo que pagaste por el inventario que hoy tienes en bodega. Entre el 2 de julio y el 8 de octubre "
            "de 2025 vendiste $10,2 M: a ese ritmo, tardaría más de un año en venderse.")
        assert metrics(it) == {"Mercancía a costo": 47_620_000, "Vendido en el periodo": 10_234_700,
                               "Meses de inventario": 21.0}
        assert it["how"]["tables"] == ["Productos", "Ventas"]
        assert it["how"]["rows_used"] == 70     # 30 productos + 40 ventas
        assert it["how"]["notes"] == []
        assert it["how"]["steps"][0] == (
            "Multipliqué las existencias de cada producto por su costo de compra (30 productos).")
        assert it["how"]["steps"][1] == "Sumé el costo de lo que vendiste en el periodo (40 ventas)."

    def test_productos_estrella(self, result):
        it = item(result, "productos_estrella")
        assert it["severity"] == "info" and it["kind"] == "opportunity"
        assert it["title"] == "Tus 3 productos estrella dejan el 36 % de tu utilidad"
        assert it["sentence"] == (
            "Son Cemento Argos 50kg ($370.500), Pintura vinilo blanco 5gal ($324.000) y Varilla corrugada 1/2 x "
            "6m ($302.500). Juntos dejan $997.000 de los $2,7 M que ganaste con todas tus ventas.")
        assert metrics(it) == {"Utilidad de los productos estrella": 997_000, "Parte de la utilidad total": 36.3,
                               "Utilidad total": 2_746_700}

    def test_reposicion_ninguno_se_agota(self, result):
        it = item(result, "reposicion")
        assert it["severity"] == "info"
        assert it["sentence"] == "Al ritmo que vendes, todos tus productos te alcanzan para 15 días o más."
        assert metrics(it) == {"Productos por agotarse": 0}

    def test_clientes_concentracion(self, result):
        it = item(result, "clientes_concentracion")
        assert it["severity"] == "info"
        assert it["sentence"] == (
            "Tus 3 mejores clientes suman el 37 % de lo que vendes y el primero, Constructora Andes SAS, el 16 %: "
            "ninguno pesa demasiado.")
        assert metrics(it) == {"Los 3 mejores clientes": 37.5, "El mejor cliente": 15.5, "Clientes distintos": 22}
        assert it["how"]["rows_used"] == 40

    def test_sin_movimiento(self, result):
        it = item(result, "sin_movimiento")
        assert it["severity"] == "info"
        assert it["sentence"] == (
            "Es plata de 1 producto que no vendiste en los últimos 90 días, sobre todo Regadera plastica 10L "
            "($360.000).")
        assert metrics(it) == {"Plata parada": 360_000, "Productos sin movimiento": 1, "Parte de tu mercancía": 0.8}

    def test_margen_bajo_ninguno(self, result):
        it = item(result, "margen_bajo")
        assert it["severity"] == "info"
        assert metrics(it) == {"Productos con margen bajo": 0}
        assert it["sentence"] == ("Ninguno de los que vendiste deja menos de 10 % de margen ni se vendió por "
                                  "debajo de su costo.")

    def test_resumen_para_whatsapp(self, result):
        lines = result["summary_text"].split("\n")
        assert lines[0] == "Resumen de tu negocio (lunes 20 de octubre)"
        assert lines[1].startswith("• Tienes $47,6 M en mercancía. Es lo que pagaste por el inventario")
        assert all(l.startswith("• ") for l in lines[1:-1])
        assert len(lines) == 8
        assert lines[-1] == "Calculado con tus ventas entre el 2 de julio y el 8 de octubre de 2025."
        assert "**" not in result["summary_text"] and "#" not in result["summary_text"]

    async def test_datos_viejos_se_avisan_frente_a_hoy(self, backend):
        await load_ferreteria(backend)
        result = await run(now=datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc))
        note = "Tu última venta registrada es del 8 de octubre de 2025: si ya vendiste después, sube el archivo actualizado."
        assert note in item(result, "capital_inventario")["how"]["notes"]
        # el calculo de "sin movimiento" NO depende de hoy: mismo resultado
        assert metrics(item(result, "sin_movimiento"))["Plata parada"] == 360_000

    async def test_solo_las_tablas_de_la_org_cuentan_proveedores_y_movimientos_se_ignoran(self, backend):
        await load_ferreteria(backend)
        result = await run()
        assert result["period"]["days"] == 99
        assert {t for i in result["items"] for t in i["how"]["tables"]} == {"Productos", "Ventas"}


# ===========================================================================
# Caso sintetico resuelto a mano (cada receta con valores no triviales)
# ===========================================================================

# Productos (costo, stock): Alfa 100/10, Beta 200/3, Gamma 50/1000, Delta 1000/5 (nunca vendido), Epsilon 100/0.
# Ventas en 10 dias (2025-03-01..2025-03-10):
#   03-01 Alfa 10 @150 (Xavier) | 03-02 Beta 10 @300 (Yolanda) | 03-05 Beta 10 @300 (Yolanda)
#   03-08 Gamma 10 @40 (Zoila, bajo el costo) | 03-10 Epsilon 5 @105 (Wilson)
# Mercancia = 1000+600+50000+5000+0 = 56.600; vendido = 1500+6000+400+525 = 8.425; costo vendido =
# 1000+4000+500+500 = 6.000; meses = 56600 x 10 / (6000 x 30) = 3,144.
# Utilidad: Alfa 500, Beta 2000, Gamma -100, Epsilon 25 (total 2.425; los 3 estrella suman 2.525 > total).
# Ritmo/dia y dias restantes: Alfa 1 -> 10; Beta 2 -> 1,5; Epsilon 0,5 con stock 0 -> 0; Gamma 1 -> 1000.
S1_PRODUCTOS = prods(("Alfa", 100, 10), ("Beta", 200, 3), ("Gamma", 50, 1000), ("Delta", 1000, 5),
                     ("Epsilon", 100, 0))
S1_VENTAS = sales(("2025-03-01", "Alfa", 10, 150, "Xavier"), ("2025-03-02", "Beta", 10, 300, "Yolanda"),
                  ("2025-03-05", "Beta", 10, 300, "Yolanda"), ("2025-03-08", "Gamma", 10, 40, "Zoila"),
                  ("2025-03-10", "Epsilon", 5, 105, "Wilson"))


class TestCasoSintetico:
    @pytest.fixture
    async def result(self, backend):
        await load(backend, S1_PRODUCTOS, S1_VENTAS)
        return await run()

    def test_orden_por_severidad_y_luego_impacto(self, result):
        assert [(i["id"], i["severity"]) for i in result["items"]] == [
            ("reposicion", "important"), ("margen_bajo", "important"), ("clientes_concentracion", "attention"),
            ("capital_inventario", "info"), ("sin_movimiento", "info"), ("productos_estrella", "info")]
        assert result["period"] == {"from": "2025-03-01", "to": "2025-03-10", "days": 10}

    def test_capital(self, result):
        it = item(result, "capital_inventario")
        assert metrics(it) == {"Mercancía a costo": 56_600, "Vendido en el periodo": 8_425,
                               "Meses de inventario": 3.1}
        assert it["sentence"] == ("Es lo que pagaste por el inventario que hoy tienes en bodega. Entre el 1 de "
                                  "marzo y el 10 de marzo de 2025 vendiste $8.425: a ese ritmo, tardaría unos 3 "
                                  "meses en venderse.")
        assert "El periodo de ventas es corto (10 días): la cifra puede cambiar con más historia." in (
            it["how"]["notes"])

    def test_reposicion(self, result):
        it = item(result, "reposicion")
        assert it["title"] == "3 productos se te agotan en menos de 15 días"
        assert it["sentence"] == ("Al ritmo que vendes se acaban: Epsilon (ya se agotó), Beta (en 1 día) y "
                                  "Alfa (en 10 días).")
        assert metrics(it) == {"Productos por agotarse": 3, "Más urgente": "Epsilon", "Días que le quedan": 0}
        assert it["action"] == "Haz hoy el pedido de Epsilon a tu proveedor."

    def test_margen_bajo(self, result):
        it = item(result, "margen_bajo")
        assert it["title"] == "2 productos te dejan muy poca ganancia"
        assert it["sentence"] == ("Los que más preocupan: Gamma (vendido por debajo de su costo) y Epsilon "
                                  "(margen 4,8 %). Las ventas bajo el costo te hicieron perder $100.")
        assert metrics(it) == {"Productos con margen bajo": 2, "Productos vendidos con pérdida": 1,
                               "Pérdida en ventas bajo el costo": 100}

    def test_clientes(self, result):
        it = item(result, "clientes_concentracion")
        assert it["sentence"] == ("Solo Yolanda, el primero, es el 71 % de lo que vendes: depender de pocos "
                                  "clientes te deja expuesto si alguno deja de comprar.")
        assert it["title"] == "Tus 3 mejores clientes son el 95 % de tus ventas"
        assert metrics(it) == {"Los 3 mejores clientes": 95.3, "El mejor cliente": 71.2, "Clientes distintos": 4}

    def test_sin_movimiento_con_periodo_corto(self, result):
        it = item(result, "sin_movimiento")
        assert it["sentence"] == ("Es plata de 1 producto que no vendiste en todo el periodo (10 días), sobre "
                                  "todo Delta ($5.000).")
        assert metrics(it) == {"Plata parada": 5_000, "Productos sin movimiento": 1, "Parte de tu mercancía": 8.8}
        assert "Tus ventas cubren solo 10 días: usé todo el periodo en lugar de 90 días." in it["how"]["notes"]

    def test_estrella_cuando_otros_pierden_plata(self, result):
        it = item(result, "productos_estrella")
        assert it["title"] == "Tus 3 productos estrella sostienen tu utilidad"
        assert it["sentence"] == (
            "Son Beta ($2.000), Alfa ($500) y Epsilon ($25). Juntos dejan $2.525, más que toda tu utilidad "
            "($2.425), porque otros productos te hacen perder plata.")
        assert metrics(it)["Utilidad total"] == 2_425

    async def test_estrella_cuando_la_utilidad_total_es_negativa(self, backend):
        # A deja +50 y B pierde 250: utilidad total -200, pero A sigue siendo el producto estrella
        await load(backend, prods(("A", 100, 10), ("B", 100, 10)),
                   sales(("2025-03-01", "A", 1, 150), ("2025-03-02", "B", 5, 50)))
        it = item(await run(), "productos_estrella")
        assert it["title"] == "Tu producto estrella deja $50"
        assert it["sentence"] == "Es A. Aun así, en total tus productos pierden plata (-$200)."
        assert metrics(it) == {"Utilidad de los productos estrella": 50, "Utilidad total": -200}

    async def test_numeros_como_texto_dan_exactamente_lo_mismo(self, backend, result):
        # misma organizacion en otra org con TODOS los numeros guardados como texto (cargas antiguas)
        await load(backend, stringify(S1_PRODUCTOS), stringify(S1_VENTAS), org=ORG_B)
        assert await run(org=ORG_B) == result


# ===========================================================================
# Orden y redaccion: el titulo es el titular; la frase aporta contexto sin repetirlo
# ===========================================================================

def _letters(text: str) -> str:
    return svc.fold(text).replace(" ", "")


def assert_titulo_y_frase_distintos(result: dict) -> None:
    for it in result["items"]:
        title, sentence = _letters(it["title"]), _letters(it["sentence"])
        assert sentence[:25] != title[:25], (it["id"], it["title"], it["sentence"])
        assert not sentence.startswith(title), (it["id"], it["title"], it["sentence"])
        # la cifra principal del titular no puede ser el arranque de la frase
        first_words = " ".join(it["sentence"].split()[:3])
        assert not any(tok in first_words for tok in it["title"].split() if tok.startswith("$")), it["id"]


def assert_orden(result: dict) -> None:
    rank = {"important": 0, "attention": 1, "info": 2}
    keys = [(rank[i["severity"]], 0 if i["action"] else 1) for i in result["items"]]
    assert keys == sorted(keys), [(i["id"], i["severity"], i["action"]) for i in result["items"]]


_ESCENARIOS = {
    "sintetico": (S1_PRODUCTOS, S1_VENTAS),
    "todo_bien": (prods(("A", 100, 1000)), sales(("2025-03-01", "A", 1, 150, "C1"), ("2025-03-02", "A", 1, 150, "C2"),
                                                  ("2025-03-03", "A", 1, 150, "C3"), ("2025-03-04", "A", 1, 150, "C4"),
                                                  ("2025-03-05", "A", 1, 150, "C5"), ("2025-03-06", "A", 1, 150, "C6"),
                                                  ("2025-03-07", "A", 1, 150, "C7"), ("2025-03-08", "A", 1, 150, "C8"))),
    "utilidad_negativa": (prods(("A", 100, 10), ("B", 100, 10)),
                          sales(("2025-03-01", "A", 1, 150), ("2025-03-02", "B", 5, 50))),
    "un_cliente": (prods(("A", 100, 10)), sales(("2025-03-01", "A", 1, 150, "Unico"), ("2025-03-02", "A", 1, 150, "Unico"))),
    "sin_ventas_con_costo": (prods(("A", 0, 10)), sales(("2025-03-01", "A", 1, 150, "C"))),
    "reposicion_muchos": (prods(*[(f"P{i}", 10, 1) for i in range(8)], ("Q", 10, 5000)),
                          sales(*[("2025-03-01", f"P{i}", 5, 20, "C") for i in range(8)], ("2025-03-10", "Q", 1, 20, "C"))),
}


class TestOrdenYRedaccion:
    @pytest.mark.parametrize("escenario", list(_ESCENARIOS))
    async def test_escenarios(self, backend, escenario):
        productos, ventas = _ESCENARIOS[escenario]
        await load(backend, productos, ventas)
        result = await run()
        assert result["items"]
        assert_titulo_y_frase_distintos(result)
        assert_orden(result)

    async def test_ferreteria(self, backend):
        await load_ferreteria(backend)
        result = await run()
        assert_titulo_y_frase_distintos(result)
        assert_orden(result)
        # el top 3 son hallazgos con contenido; los "todo bien" van al final
        assert [i["id"] for i in result["items"][:3]] == ["capital_inventario", "sin_movimiento",
                                                          "clientes_concentracion"]
        assert [i["id"] for i in result["items"][-2:]] == ["reposicion", "margen_bajo"]
        assert all(i["action"] is None for i in result["items"][-2:])

    @pytest.mark.parametrize("seed", range(25))
    async def test_datos_aleatorios(self, backend, seed):
        productos, ventas = _random_case(seed)
        await load(backend, productos, ventas)
        result = await run()
        assert_titulo_y_frase_distintos(result)
        assert_orden(result)

    async def test_los_todo_bien_van_despues_de_los_informativos_con_contenido(self, backend):
        # reposicion "todo bien" (info sin action) debe quedar detras de estrella/clientes (info con action)
        await load(backend, *_ESCENARIOS["todo_bien"])
        ids = [(i["id"], i["action"] is not None) for i in (await run())["items"]]
        con_accion = [x for x in ids if x[1]]
        assert ids[:len(con_accion)] == con_accion

    def test_la_regla_detecta_una_frase_que_repite_el_titulo(self):
        malo = {"items": [{"id": "x", "title": "Tienes $47,6 M en mercancía",
                           "sentence": "Tienes $47,6 M en mercancía (a costo). Algo más."}]}
        with pytest.raises(AssertionError):
            assert_titulo_y_frase_distintos(malo)


# ===========================================================================
# Umbrales exactos (cada comparacion estricta, en ambos lados del limite)
# ===========================================================================

def _inventory_case(stock: int, sold: int):
    """Periodo de exactamente 30 dias (mes = 1): meses de inventario = stock / vendido (costo 100, precio 150)."""
    return (prods(("P", 100, stock)),
            sales(("2025-03-01", "P", sold, 150, "C"), ("2025-03-30", "P", 0 + 1, 150, "C")))


class TestUmbrales:
    @pytest.mark.parametrize("stock,sold,severity,months", [
        (60, 9, "info", 6.0),          # 60 / (9+1) = 6 exacto: NO supera 6
        (61, 9, "attention", 6.1),
        (120, 9, "attention", 12.0),   # 12 exacto: NO supera 12
        (121, 9, "important", 12.1),
        (5, 9, "info", 0.5),
    ])
    async def test_meses_de_inventario(self, backend, stock, sold, severity, months):
        productos, ventas = _inventory_case(stock, sold)
        await load(backend, productos, ventas)
        result = await run()
        assert result["period"]["days"] == 30
        it = item(result, "capital_inventario")
        assert (it["severity"], metrics(it)["Meses de inventario"]) == (severity, months)

    @pytest.mark.parametrize("stock,listed,severity", [
        (15, False, "info"),          # 15,0 dias exactos: NO es "< 15"
        (14, True, "attention"),      # 14,0 dias
        (7, True, "attention"),       # 7,0 dias exactos: NO es "< 7"
        (6, True, "important"),       # 6,0 dias
    ])
    async def test_reposicion_limites_de_15_y_7_dias(self, backend, stock, listed, severity):
        # periodo de 10 dias y 10 unidades vendidas de P: dias restantes = stock x 10 / 10 = stock
        await load(backend, prods(("P", 10, stock), ("Q", 10, 1000)),
                   sales(("2025-03-01", "P", 10, 20), ("2025-03-10", "Q", 1, 20)))
        it = item(await run(), "reposicion")
        assert (it["metrics"][0]["value"] == 1) == listed
        assert it["severity"] == severity
        if listed:
            assert it["sentence"] == f"Al ritmo que vendes se acaba: P (en {stock} días)."

    async def test_reposicion_ritmo_cero_se_excluye_y_no_divide_por_cero(self, backend):
        # P no se vende (ritmo 0), con poco stock: no aparece; Q si se vende
        await load(backend, prods(("P", 10, 1), ("Q", 10, 1000)),
                   sales(("2025-03-01", "Q", 1, 20), ("2025-03-10", "Q", 1, 20)))
        assert metrics(item(await run(), "reposicion")) == {"Productos por agotarse": 0}

    @staticmethod
    def _clients(shares):
        """shares: ventas por cliente (un solo producto); periodo de 2 dias."""
        ventas = []
        for i, amount in enumerate(shares):
            ventas.append({"fecha": "2025-03-01" if i % 2 == 0 else "2025-03-02", "producto": "P", "cantidad": 1,
                           "precio_unitario": amount, "total": amount, "cliente": f"Cliente {i}"})
        return prods(("P", 1, 10)), ventas

    @pytest.mark.parametrize("shares,severity", [
        ([300, 100, 100, 100, 100, 100, 100, 100], "info"),         # primero 30 % exacto y top3 50 % exacto
        ([301, 100, 100, 100, 100, 100, 100, 99], "attention"),      # primero 30,1 %
        ([200, 150, 150, 100, 100, 100, 100, 100], "info"),          # top3 50 % exacto
        ([200, 150, 151, 100, 100, 100, 100, 99], "attention"),      # top3 50,1 % y primero 20 %
        ([100] * 10, "info"),
    ])
    async def test_concentracion_de_clientes(self, backend, shares, severity):
        assert sum(shares) == 1000
        productos, ventas = self._clients(shares)
        await load(backend, productos, ventas)
        it = item(await run(), "clientes_concentracion")
        assert it["severity"] == severity

    @pytest.mark.parametrize("price,flagged,loses", [
        (100, False, False),      # margen 10 % exacto
        (99, True, False),        # 9,09 %
        (90, True, False),        # precio = costo: margen 0, no es "bajo el costo"
        (89, True, True),         # bajo el costo
    ])
    async def test_margen_bajo_10_por_ciento_y_bajo_costo(self, backend, price, flagged, loses):
        # costo 90
        await load(backend, prods(("P", 90, 5)), sales(("2025-03-01", "P", 2, price, "C")))
        it = item(await run(), "margen_bajo")
        assert (it["metrics"][0]["value"] > 0) == flagged
        assert (it["severity"] == "important") == loses

    async def test_ventana_de_90_dias_incluye_el_dia_89_y_excluye_el_90(self, backend):
        # ultima fecha 2025-03-31: la ventana es 2025-01-01..2025-03-31 (90 dias contados desde la ultima venta)
        await load(
            backend,
            prods(("Dentro", 10, 1), ("Fuera", 10, 1), ("Ultimo", 10, 1)),
            sales(("2025-01-01", "Dentro", 1, 20), ("2024-12-31", "Fuera", 1, 20), ("2025-03-31", "Ultimo", 1, 20)),
        )
        it = item(await run(), "sin_movimiento")
        assert metrics(it)["Productos sin movimiento"] == 1
        assert "Fuera ($10)" in it["sentence"]
        assert "Tus ventas cubren solo" not in " ".join(it["how"]["notes"])

    async def test_sin_movimiento_es_relativo_a_la_ultima_venta_no_a_hoy(self, backend):
        await load(backend, prods(("P", 10, 1), ("Q", 10, 1)),
                   sales(("2025-03-01", "P", 1, 20), ("2025-03-02", "Q", 1, 20)))
        a = await run(now=datetime(2025, 3, 3, 12, tzinfo=timezone.utc))
        b = await run(now=datetime(2030, 1, 1, 12, tzinfo=timezone.utc))
        assert item(a, "sin_movimiento")["metrics"] == item(b, "sin_movimiento")["metrics"]

    @pytest.mark.parametrize("percent_parked,severity", [(20, "attention"), (19, "info")])
    async def test_sin_movimiento_atencion_desde_20_por_ciento_de_la_mercancia(self, backend, percent_parked, severity):
        # mercancia total 100 (a costo 1): parado = percent_parked unidades
        await load(backend, prods(("Parado", 1, percent_parked), ("Vendido", 1, 100 - percent_parked)),
                   sales(("2025-03-01", "Vendido", 1, 2), ("2025-03-02", "Vendido", 1, 2)))
        assert item(await run(), "sin_movimiento")["severity"] == severity


class TestLimitesDePeriodo:
    @pytest.mark.parametrize("last,short", [("2025-04-29", False), ("2025-04-28", True)])
    async def test_periodo_corto_es_menor_a_60_dias(self, backend, last, short):
        # 2025-03-01 .. 2025-04-29 son exactamente 60 dias (ambos extremos incluidos)
        await load(backend, prods(("P", 100, 10)), sales(("2025-03-01", "P", 1, 150), (last, "P", 1, 150)))
        result = await run()
        notes = " ".join(item(result, "capital_inventario")["how"]["notes"])
        assert ("El periodo de ventas es corto" in notes) == short

    @pytest.mark.parametrize("now_day,stale", [("2025-05-09", False), ("2025-05-10", True)])
    async def test_datos_viejos_se_avisan_desde_mas_de_60_dias(self, backend, now_day, stale):
        await load(backend, prods(("P", 100, 10)), sales(("2025-03-01", "P", 1, 150), ("2025-03-10", "P", 1, 150)))
        y, m, d = map(int, now_day.split("-"))
        result = await run(now=datetime(y, m, d, 15, 0, tzinfo=timezone.utc))
        notes = " ".join(item(result, "capital_inventario")["how"]["notes"])
        assert ("Tu última venta registrada es del 10 de marzo de 2025" in notes) == stale

    @pytest.mark.parametrize("last,whole_period", [("2025-03-31", False), ("2025-03-30", True)])
    async def test_ventana_de_90_dias_vs_periodo_completo(self, backend, last, whole_period):
        # 2025-01-01 .. 2025-03-31 son exactamente 90 dias: la ventana ES todo el periodo pero no hay nada que avisar
        await load(backend, prods(("P", 100, 10), ("Q", 100, 10)),
                   sales(("2025-01-01", "P", 1, 150), (last, "Q", 1, 150)))
        notes = " ".join(item(await run(), "sin_movimiento")["how"]["notes"])
        if whole_period:
            assert "Tus ventas cubren solo 89 días: usé todo el periodo en lugar de 90 días." in notes
        else:
            assert "Tus ventas cubren solo" not in notes

    async def test_el_dinero_se_redondea_comercialmente(self, backend):
        # 100,5 de mercancia: $101 (la mitad se aleja de cero), no $100 (redondeo al par)
        await load(backend, prods(("A", 100.5, 1)), sales(("2025-03-01", "A", 1, 200)))
        capital = item(await run(), "capital_inventario")
        assert metrics(capital)["Mercancía a costo"] == 101
        assert capital["title"] == "Tienes $101 en mercancía"


# ===========================================================================
# Que falta (missing) y rol que no aparece
# ===========================================================================

class TestMissing:
    async def test_sin_ninguna_tabla_todo_va_a_missing_con_lenguaje_simple(self, backend):
        result = await run()
        assert result["items"] == [] and result["period"] is None
        assert [m["id"] for m in result["missing"]] == ALL_RECIPES + ["cartera"]
        assert missing(result, "capital_inventario")["needs"] == (
            "Necesito una hoja de productos con costo (precio de compra) y existencias (stock). "
            "Necesito una hoja de ventas con fecha, producto, cantidad y valor (total o precio unitario).")
        assert missing(result, "clientes_concentracion")["needs"] == (
            "Necesito una hoja de ventas con fecha, cantidad, valor (total o precio unitario) y cliente.")
        assert result["summary_text"].startswith("Resumen de tu negocio (lunes 20 de octubre)\n• Todavía no puedo")

    async def test_solo_ventas_calcula_clientes_y_pide_productos_para_el_resto(self, backend):
        await load(backend, None, S1_VENTAS)
        result = await run()
        assert [i["id"] for i in result["items"]] == ["clientes_concentracion"]
        assert missing(result, "reposicion")["needs"] == (
            "Necesito una hoja de productos con existencias (stock).")
        assert missing(result, "margen_bajo")["needs"] == (
            "Necesito una hoja de productos con costo (precio de compra).")

    async def test_solo_productos_pide_ventas(self, backend):
        await load(backend, S1_PRODUCTOS, None)
        result = await run()
        assert result["items"] == []
        assert missing(result, "reposicion")["needs"] == "Necesito una hoja de ventas con fecha, producto y cantidad."
        assert missing(result, "margen_bajo")["needs"] == (
            "Necesito una hoja de ventas con fecha, producto, cantidad y valor (total o precio unitario).")

    async def test_productos_sin_columna_de_existencias(self, backend):
        sin_stock = [{k: v for k, v in r.items() if k != "stock"} for r in S1_PRODUCTOS]
        await load(backend, sin_stock, S1_VENTAS, pcols={"nombre": "text", "costo": "number"})
        result = await run()
        ids = {i["id"] for i in result["items"]}
        assert ids == {"productos_estrella", "margen_bajo", "clientes_concentracion"}
        needs = missing(result, "capital_inventario")["needs"]
        assert needs == "A tu hoja de productos ('Productos') le falta: existencias (stock)."
        assert missing(result, "reposicion")["needs"] == needs

    async def test_productos_sin_columna_de_costo(self, backend):
        sin_costo = [{k: v for k, v in r.items() if k != "costo"} for r in S1_PRODUCTOS]
        await load(backend, sin_costo, S1_VENTAS, pcols={"nombre": "text", "stock": "integer"})
        result = await run()
        assert {i["id"] for i in result["items"]} == {"reposicion", "clientes_concentracion"}
        assert missing(result, "productos_estrella")["needs"] == (
            "A tu hoja de productos ('Productos') le falta: costo (precio de compra).")

    async def test_ventas_sin_cliente(self, backend):
        sin = [{k: v for k, v in r.items() if k != "cliente"} for r in S1_VENTAS]
        await load(backend, S1_PRODUCTOS, sin, vcols={k: v for k, v in SALE_COLS.items() if k != "cliente"})
        result = await run()
        assert "clientes_concentracion" not in {i["id"] for i in result["items"]}
        assert missing(result, "clientes_concentracion")["needs"] == (
            "A tu hoja de ventas ('Ventas') le falta: cliente.")

    async def test_cliente_vacio_o_generico_no_cuenta(self, backend):
        ventas = [{**r, "cliente": "Mostrador" if i % 2 else ""} for i, r in enumerate(S1_VENTAS)]
        ventas = [{k: v for k, v in r.items() if v != ""} for r in ventas]
        await load(backend, S1_PRODUCTOS, ventas)
        result = await run()
        assert "clientes_concentracion" not in {i["id"] for i in result["items"]}
        assert "Una columna de cliente con nombres" in missing(result, "clientes_concentracion")["needs"]

    async def test_hoja_de_cartera_existente_no_se_pide(self, backend):
        await load(backend, S1_PRODUCTOS, S1_VENTAS)
        await backend.add_table("por_cobrar", {"cliente": "text", "saldo": "number", "fecha_vencimiento": "date"},
                                [{"cliente": "Xavier", "saldo": 5, "fecha_vencimiento": "2025-04-01"}])
        result = await run()
        assert [m["id"] for m in result["missing"]] == []

    async def test_estrella_sin_utilidad_positiva_va_a_missing(self, backend):
        await load(backend, prods(("P", 100, 5)), sales(("2025-03-01", "P", 2, 80, "C")))
        result = await run()
        assert "productos_estrella" not in {i["id"] for i in result["items"]}
        assert "ningún producto deja ganancia" in missing(result, "productos_estrella")["needs"]


# ===========================================================================
# Robustez: datos raros nunca dan 500; degradan a missing / notes
# ===========================================================================

class TestRobustez:
    async def test_tablas_vacias(self, backend):
        await load(backend, [], [])
        result = await run()
        assert result["items"] == [] and result["period"] is None
        assert "vacía" in missing(result, "capital_inventario")["needs"]
        assert "vacía" in missing(result, "clientes_concentracion")["needs"]

    async def test_numeros_como_texto_con_formas_raras(self, backend):
        productos = prods(("Alfa", "35000", "45"), ("Beta", " 12000 ", "1e1"), ("Gamma", "n/a", "x"),
                          ("Delta", "$1.200", "5"))
        ventas = sales(("2025-03-01", "Alfa", 2, 52000, "C1"), ("2025-03-02", "Beta", 1, 20000, "C2"))
        ventas = stringify(ventas)
        await load(backend, productos, ventas)
        result = await run()
        capital = item(result, "capital_inventario")
        # Alfa 45 x 35000 + Beta 10 x 12000 = 1.575.000 + 120.000; Gamma y Delta sin costo legible
        assert metrics(capital)["Mercancía a costo"] == 1_695_000
        notes = " ".join(capital["how"]["notes"])
        assert "2 productos no tienen costo" in notes
        assert "1 fila sin existencias legibles no se contó" in notes      # Gamma: stock "x"

    async def test_valores_con_forma_de_miles_se_leen_como_decimal_y_se_avisan(self, backend):
        await load(backend, prods(("Alfa", "1.200", "10")), stringify(sales(("2025-03-01", "Alfa", 1, 5000, "C"))))
        capital = item(await run(), "capital_inventario")
        assert metrics(capital)["Mercancía a costo"] == 12      # 10 x 1,2: igual que el chat
        assert any("la forma '1.200'" in n for n in capital["how"]["notes"])

    async def test_nulos_y_ceros_sin_dividir_por_cero(self, backend):
        productos = prods(("Gratis", 0, 10), ("SinCosto", None, 4), ("SinStock", 50, None), ("Normal", 100, 2),
                          (None, 5, 5))
        ventas = sales(("2025-03-01", "Gratis", 3, 10), ("2025-03-01", "SinStock", 1, 70),
                       ("2025-03-02", "Normal", 0, 150),            # cantidad 0: no es una venta
                       ("2025-03-02", "Normal", 2, 150))
        await load(backend, productos, ventas)
        result = await run()
        assert result["items"]       # no revienta
        capital = item(result, "capital_inventario")
        assert metrics(capital)["Mercancía a costo"] == 200          # solo Normal: 2 x 100
        notes = " ".join(capital["how"]["notes"])
        assert "1 fila sin nombre no se contó en tu hoja de productos." in notes
        assert "1 venta sin cantidad o valor legible no se contó." in notes
        # Gratis (costo 0) y SinCosto no tienen costo: no entran en utilidad
        stars = item(result, "productos_estrella")
        assert "Gratis" not in stars["sentence"] and "SinCosto" not in stars["sentence"]

    async def test_todos_los_costos_en_cero_van_a_missing(self, backend):
        await load(backend, prods(("A", 0, 5), ("B", 0, 5)), sales(("2025-03-01", "A", 1, 10)))
        result = await run()
        assert "costo (precio de compra) de tus productos está vacío o en cero" in (
            missing(result, "capital_inventario")["needs"])
        assert {i["id"] for i in result["items"]} == {"reposicion"}

    async def test_productos_repetidos_se_suman_y_se_avisa(self, backend):
        # "Martillo" aparece 3 veces (mayusculas, espacios): 10 x 100 + 5 x 200 + 5 x 100 = 2.500; stock 20
        productos = prods(("Martillo", 100, 10), ("martillo ", 200, 5), (" MARTILLO", 100, 5), ("Otro", 10, 1))
        await load(backend, productos, sales(("2025-03-01", "Martillo", 4, 300), ("2025-03-02", "Otro", 1, 20)))
        result = await run()
        capital = item(result, "capital_inventario")
        assert metrics(capital)["Mercancía a costo"] == 2_510
        assert "1 producto aparece repetido en tu hoja de productos: sumé sus existencias y usé el costo promedio." in (
            capital["how"]["notes"])
        assert capital["how"]["steps"][0].endswith("(2 productos).")
        # costo promedio ponderado por existencias = 2500 / 20 = 125; utilidad Martillo = 4 x (300 - 125) = 700
        assert metrics(item(result, "productos_estrella"))["Utilidad total"] == 700 + 10

    async def test_fechas_en_varios_formatos(self, backend):
        ventas = [
            {"fecha": "2025-03-01", "producto": "A", "cantidad": 1, "precio_unitario": 10},
            {"fecha": "05/03/2025", "producto": "A", "cantidad": 1, "precio_unitario": 10},        # 5 de marzo
            {"fecha": "2025-03-07 14:30:00", "producto": "A", "cantidad": 1, "precio_unitario": 10},
            {"fecha": "9-3-2025", "producto": "A", "cantidad": 1, "precio_unitario": 10},
            {"fecha": "ayer", "producto": "A", "cantidad": 1, "precio_unitario": 10},
            {"producto": "A", "cantidad": 1, "precio_unitario": 10},                              # sin fecha
        ]
        await load(backend, prods(("A", 5, 50)), ventas)
        result = await run()
        assert result["period"] == {"from": "2025-03-01", "to": "2025-03-09", "days": 9}
        notes = " ".join(item(result, "capital_inventario")["how"]["notes"])
        assert "2 ventas sin fecha legible no se contaron." in notes
        assert metrics(item(result, "capital_inventario"))["Vendido en el periodo"] == 40

    async def test_fechas_imposibles_no_estiran_el_periodo(self, backend):
        ventas = sales(("2025-03-01", "A", 1, 10), ("2025-03-05", "A", 1, 10), ("1900-01-01", "A", 1, 10),
                       ("2999-01-01", "A", 1, 10))
        await load(backend, prods(("A", 5, 50)), ventas)
        result = await run()
        assert result["period"] == {"from": "2025-03-01", "to": "2025-03-05", "days": 5}
        assert "2 ventas con una fecha imposible no se contaron (antes del año 2000 o más de un año en el futuro)." in (
            item(result, "capital_inventario")["how"]["notes"])

    async def test_un_solo_dia_de_ventas(self, backend):
        await load(backend, prods(("A", 100, 10)), sales(("2025-03-01", "A", 5, 150, "C")))
        result = await run()
        assert result["period"] == {"from": "2025-03-01", "to": "2025-03-01", "days": 1}
        repo = item(result, "reposicion")
        assert repo["sentence"] == "Al ritmo que vendes se acaba: A (en 2 días)."      # 5/dia -> 10 / 5
        assert "El periodo de ventas es corto (1 día)" in " ".join(repo["how"]["notes"])
        # meses = 1000 x 1 dia / (costo vendido 500 x 30) = 0,067
        assert metrics(item(result, "capital_inventario"))["Meses de inventario"] == 0.1

    async def test_valores_enormes(self, backend):
        await load(backend, prods(("A", 10**9, 10**12)), sales(("2025-03-01", "A", 1, 10**10, "C")))
        result = await run()
        capital = item(result, "capital_inventario")
        assert metrics(capital)["Mercancía a costo"] == 10**21
        assert capital["title"] == "Tienes $1.000.000.000 billones en mercancía"

    async def test_acentos_y_mayusculas_distintos_entre_hojas(self, backend):
        await load(backend, prods(("Cañería Ñandú", 10, 5), ("Árbol", 20, 5)),
                   sales(("2025-03-01", "CAÑERIA ñandu", 1, 15, "C"), ("2025-03-02", "arbol ", 1, 30, "C")))
        result = await run()
        assert not [n for i in result["items"] for n in i["how"]["notes"] if "no están en tu hoja" in n]
        assert metrics(item(result, "productos_estrella"))["Utilidad total"] == 15

    async def test_ventas_de_productos_que_no_existen(self, backend):
        ventas = sales(("2025-03-01", "Alfa", 1, 150), ("2025-03-02", "Fantasma", 3, 100),
                       ("2025-03-03", "Fantasma", 2, 100), ("2025-03-03", "Otro Inexistente", 1, 50))
        await load(backend, prods(("Alfa", 100, 10)), ventas)
        result = await run()
        # se cuentan ventas (filas), no unidades
        note = ("3 ventas de 2 productos que no están en tu hoja de productos (por ejemplo 'Fantasma' y 'Otro "
                "Inexistente'): no entran en los cálculos de costo y utilidad.")
        for rid in ("capital_inventario", "productos_estrella", "reposicion", "margen_bajo"):
            assert note in item(result, rid)["how"]["notes"], rid
        assert metrics(item(result, "productos_estrella"))["Utilidad total"] == 50        # solo Alfa
        assert metrics(item(result, "capital_inventario"))["Vendido en el periodo"] == 150 + 300 + 200 + 50

    async def test_existencias_negativas_cuentan_cero(self, backend):
        await load(backend, prods(("Alfa", 100, -5), ("Beta", 100, 3)), sales(("2025-03-01", "Alfa", 1, 150)))
        capital = item(await run(), "capital_inventario")
        assert metrics(capital)["Mercancía a costo"] == 300
        assert "1 fila tiene existencias negativas: la conté como 0." in capital["how"]["notes"]

    async def test_devoluciones_con_cantidad_negativa_no_cuentan(self, backend):
        await load(backend, prods(("Alfa", 100, 10)),
                   sales(("2025-03-01", "Alfa", 2, 150), ("2025-03-02", "Alfa", -1, 150)))
        capital = item(await run(), "capital_inventario")
        assert metrics(capital)["Vendido en el periodo"] == 300
        assert "1 venta sin cantidad o valor legible no se contó." in capital["how"]["notes"]

    async def test_solo_total_el_precio_real_es_total_sobre_cantidad(self, backend):
        # sin columna de precio unitario: precio real = total / cantidad = 80; costo 100 -> vendido bajo el costo
        ventas = [{"fecha": "2025-03-01", "producto": "A", "cantidad": 4, "total": 320}]
        await load(backend, prods(("A", 100, 10)), ventas,
                   vcols={"fecha": "date", "producto": "text", "cantidad": "integer", "total": "number"})
        result = await run()
        margen = item(result, "margen_bajo")
        assert margen["severity"] == "important"
        assert metrics(margen)["Pérdida en ventas bajo el costo"] == 80       # 4 x (100 - 80)
        assert metrics(item(result, "capital_inventario"))["Vendido en el periodo"] == 320

    async def test_fila_sin_precio_unitario_usa_total_sobre_cantidad(self, backend):
        ventas = [{"fecha": "2025-03-01", "producto": "A", "cantidad": 2, "precio_unitario": 150, "total": 300},
                  {"fecha": "2025-03-02", "producto": "A", "cantidad": 2, "total": 400},         # precio 200
                  {"fecha": "2025-03-03", "producto": "A", "cantidad": 2}]                       # sin valor
        await load(backend, prods(("A", 100, 10)), ventas)
        capital = item(await run(), "capital_inventario")
        assert metrics(capital)["Vendido en el periodo"] == 300 + 400
        assert "1 venta sin cantidad o valor legible no se contó." in capital["how"]["notes"]

    async def test_dos_hojas_de_ventas_no_se_mezclan(self, backend):
        cols = ["fecha", "producto", "cantidad", "precio_unitario", "total"]
        viejas = sales(("2024-01-01", "A", 100, 10), ("2024-02-01", "A", 100, 10))
        nuevas = sales(("2025-03-01", "A", 1, 150, "C1"), ("2025-03-05", "A", 1, 150, "C2"))
        await backend.add_table("ventas_2024", {c: SALE_COLS[c] for c in cols}, viejas, display="Ventas 2024")
        await backend.add_table("ventas", SALE_COLS, nuevas, display="Ventas")
        await load(backend, prods(("A", 100, 10)))
        result = await run()
        assert result["period"]["from"] == "2025-03-01"
        capital = item(result, "capital_inventario")
        assert metrics(capital)["Vendido en el periodo"] == 300
        assert capital["how"]["tables"] == ["Productos", "Ventas"]
        assert any("También encontré la hoja 'Ventas 2024' que parece de ventas" in n for n in capital["how"]["notes"])

    async def test_nombres_de_hoja_y_de_columna_arbitrarios(self, backend):
        productos = [{"Descripción": "Taladro", "Precio de Compra": 100, "Existencias": 10},
                     {"Descripción": "Martillo", "Precio de Compra": 10, "Existencias": 3}]
        ventas = [{"Fecha Venta": "2025-03-01", "Artículo": "TALADRO", "Unidades": 2, "Valor Total": 300,
                   "Cliente": "Ana"},
                  {"Fecha Venta": "2025-03-05", "Artículo": "martillo", "Unidades": 1, "Valor Total": 30,
                   "Cliente": "Luis"}]
        await backend.add_table("hoja1", {"Descripción": "text", "Precio de Compra": "number",
                                          "Existencias": "integer"}, productos, display="Mi inventario")
        await backend.add_table("hoja2", {"Fecha Venta": "date", "Artículo": "text", "Unidades": "integer",
                                          "Valor Total": "number", "Cliente": "text"}, ventas, display="Lo vendido")
        result = await run()
        capital = item(result, "capital_inventario")
        assert metrics(capital)["Mercancía a costo"] == 1_030
        assert capital["how"]["tables"] == ["Mi inventario", "Lo vendido"]
        assert [i["id"] for i in result["items"]].count("clientes_concentracion") == 1

    async def test_nombres_de_usuario_con_caracteres_de_control_salen_en_una_linea(self, backend):
        await load(backend, prods(("Mal\nNombre\t\x07" + "x" * 100, 100, 1)),
                   sales(("2025-03-01", "Mal\nNombre\t\x07" + "x" * 100, 1, 200)))
        text = item(await run(), "reposicion")["sentence"]
        assert "\n" not in text and "\t" not in text and "\x07" not in text and len(text) < 160

    async def test_columna_de_cantidad_tipo_si_no_degrada_sin_500(self, backend):
        # un tipo raro en el catalogo (cantidad "si/no"): el motor agrupa los 1 como "sí", que no es un numero:
        # no hay ventas validas y la receta degrada en vez de dar cifras inventadas
        await load(backend, S1_PRODUCTOS, sales(("2025-03-01", "Alfa", 1, 150), ("2025-03-02", "Beta", 1, 300)),
                   vcols={**SALE_COLS, "cantidad": "boolean"})
        result = await run()
        assert result["items"] == []
        assert missing(result, "capital_inventario")["needs"] == "Tus ventas no tienen cantidades y valores que pueda leer."

    async def test_movimientos_de_inventario_en_la_hoja_de_ventas_no_estiran_el_periodo(self, backend):
        # la carga real fusiona a veces inventario_movimientos dentro de ventas: filas con cantidad pero sin precio
        ventas = S1_VENTAS + [{"fecha": "2025-02-01", "producto": "Alfa", "cantidad": 100, "tipo_movimiento": "entrada"},
                              {"fecha": "2025-04-01", "producto": "Beta", "cantidad": 5, "tipo_movimiento": "salida"}]
        await load(backend, S1_PRODUCTOS, ventas, vcols={**SALE_COLS, "tipo_movimiento": "text"})
        result = await run()
        assert result["period"] == {"from": "2025-03-01", "to": "2025-03-10", "days": 10}
        notes = item(result, "capital_inventario")["how"]["notes"]
        assert "2 ventas sin cantidad o valor legible no se contaron." in notes
        assert metrics(item(result, "capital_inventario")) == {
            "Mercancía a costo": 56_600, "Vendido en el periodo": 8_425, "Meses de inventario": 3.1}

    async def test_demasiadas_combinaciones_no_da_una_cifra_parcial(self, backend):
        await load(backend, S1_PRODUCTOS, S1_VENTAS)
        with patch.object(svc, "MAX_GROUPS", 3):
            result = await run()
        assert result["items"] == []
        assert "demasiadas combinaciones distintas" in missing(result, "capital_inventario")["needs"]

    async def test_una_receta_que_falla_no_tumba_a_las_demas(self, backend):
        await load(backend, S1_PRODUCTOS, S1_VENTAS)
        with patch.object(svc, "recipe_reposicion", side_effect=ZeroDivisionError):
            with patch.object(svc, "RECIPES", tuple({**r, "fn": svc.recipe_reposicion} if r["id"] == "reposicion" else r
                                                    for r in svc.RECIPES)):
                result = await run()
        assert "reposicion" not in {i["id"] for i in result["items"]}
        assert "Revisa que tus datos" in missing(result, "reposicion")["needs"]
        assert len(result["items"]) == 5

    async def test_filas_que_no_son_objetos_no_rompen(self, backend):
        if backend.name != "postgres":
            pytest.skip("las filas jsonb no-objeto solo se pueden guardar en Postgres real")
        await load(backend, S1_PRODUCTOS + [["no", "es", "objeto"], "texto"], S1_VENTAS + [42, None])
        assert item(await run(), "capital_inventario")["metrics"][0]["value"] == 56_600

    async def test_el_resultado_es_determinista(self, backend):
        await load(backend, S1_PRODUCTOS, S1_VENTAS)
        assert await run() == await run()


# ===========================================================================
# Fallos de infraestructura: 503, nunca 500 ni cifras parciales
# ===========================================================================

class _FakeAsyncpgError(Exception):
    pass


_FakeAsyncpgError.__module__ = "asyncpg.exceptions"


class TestInfraestructura:
    async def test_error_de_postgres_es_servicio_no_disponible(self, backend):
        if backend.name != "oraculo":
            pytest.skip("se simula el fallo del motor")
        await load(backend, S1_PRODUCTOS, S1_VENTAS)

        async def boom(pool, plans):
            raise _FakeAsyncpgError("canceling statement due to statement timeout")

        with patch("app.services.data_query_engine.run_plans", boom):
            with pytest.raises(svc.InsightsUnavailable):
                await run()

    async def test_tiempo_total_agotado(self, backend):
        if backend.name != "oraculo":
            pytest.skip("se simula la lentitud del motor")
        import asyncio
        await load(backend, S1_PRODUCTOS, S1_VENTAS)

        async def slow(pool, plans):
            await asyncio.sleep(5)

        with patch("app.services.data_query_engine.run_plans", slow), patch.object(svc, "TOTAL_TIMEOUT_SECONDS", 0.05):
            with pytest.raises(svc.InsightsUnavailable):
                await run()

    async def test_un_error_de_programacion_no_se_disfraza_de_503(self, backend):
        if backend.name != "oraculo":
            pytest.skip("se simula el fallo del motor")
        await load(backend, S1_PRODUCTOS, S1_VENTAS)

        async def bug(pool, plans):
            raise KeyError("bug")

        with patch("app.services.data_query_engine.run_plans", bug):
            with pytest.raises(KeyError):
                await run()


# ===========================================================================
# Aislamiento entre organizaciones
# ===========================================================================

class TestAislamiento:
    async def test_cada_org_ve_solo_sus_datos(self, backend):
        await load(backend, S1_PRODUCTOS, S1_VENTAS, org=ORG_A)
        await load(backend, prods(("Zeta", 10, 100)), sales(("2025-05-01", "Zeta", 1, 50, "Unico"),
                                                            ("2025-05-09", "Zeta", 2, 50, "Unico")), org=ORG_B)
        a, b = await run(org=ORG_A), await run(org=ORG_B)
        assert metrics(item(a, "capital_inventario"))["Mercancía a costo"] == 56_600
        assert metrics(item(b, "capital_inventario"))["Mercancía a costo"] == 1_000
        assert a["period"]["from"] == "2025-03-01" and b["period"]["from"] == "2025-05-01"
        text_b = str(b)
        assert all(name not in text_b for name in ("Alfa", "Beta", "Yolanda", "Xavier"))
        assert "Zeta" not in str(a) and "Unico" not in str(a)

    async def test_una_org_vacia_no_ve_los_datos_de_otra(self, backend):
        await load(backend, S1_PRODUCTOS, S1_VENTAS, org=ORG_A)
        result = await run(org=ORG_B)
        assert result["items"] == [] and result["period"] is None
        assert "Alfa" not in str(result)

    async def test_el_servicio_pide_el_pool_de_la_org_que_recibe(self, backend):
        if backend.name != "oraculo":
            pytest.skip("solo la BD emulada registra los pools pedidos")
        await load(backend, S1_PRODUCTOS, S1_VENTAS, org=ORG_A)
        await run(org=ORG_A)
        await run(org=ORG_B)
        assert backend.dbs.requested_org_ids == [ORG_A, ORG_B]

    async def test_solo_lee_nunca_escribe(self, backend):
        if backend.name != "oraculo":
            pytest.skip("la bitacora SQL solo existe en la BD emulada")
        await load(backend, S1_PRODUCTOS, S1_VENTAS)
        await run()
        log = backend.dbs.db(ORG_A).sql_log
        assert log and all(q.startswith("select") for q in log), log
        assert backend.dbs.db(ORG_A).chat == []        # no toca el chat ni su cuota


# ===========================================================================
# Pruebas diferenciales contra el oraculo pandas (datos aleatorios y sucios)
# ===========================================================================

def _random_case(seed: int):
    import random
    rnd = random.Random(seed)
    names = ["Martillo", "Taladro Bosch", "Cañería PVC", "Árbol decorativo", "Cemento 50kg", "Pintura Blanca",
             "Lija #100", "Cable THW", "Clavo 2\"", "Tornillo 6x1", "Brocha 4in", "Llave 1/2"]
    productos = []
    for n in rnd.sample(names, rnd.randint(5, 11)):
        variants = [n, n.upper(), n.lower() + " ", " " + n] if rnd.random() < 0.25 else [n]
        for v in variants:
            row = {"nombre": v}
            cost = rnd.choice([rnd.randint(5, 300) * 10, str(rnd.randint(5, 300) * 10), 0, None, "n/a"])
            stock = rnd.choice([rnd.randint(0, 200), str(rnd.randint(0, 200)), -3, None, "x"])
            if cost is not None:
                row["costo"] = cost
            if stock is not None:
                row["stock"] = stock
            productos.append(row)
    ventas = []
    pool = names + ["Fantasma A", "Fantasma B"]
    clientes = ["Ana", "Luis", "Pedro", "Maria", "Constructora X", "Mostrador", "", None, "ANA ", "Ñandú SAS"]
    for _ in range(rnd.randint(20, 90)):
        row = {"fecha": rnd.choice([f"2025-{rnd.randint(1, 6):02d}-{rnd.randint(1, 28):02d}",
                                    f"{rnd.randint(1, 28):02d}/{rnd.randint(1, 6):02d}/2025", "ayer", None]),
               "producto": rnd.choice(pool) if rnd.random() < 0.9 else rnd.choice(pool).upper()}
        row["cantidad"] = rnd.choice([rnd.randint(1, 20), str(rnd.randint(1, 20)), 0, -2, "x", None])
        r = rnd.random()
        if r < 0.6:
            row["precio_unitario"] = rnd.choice([rnd.randint(5, 400) * 10, str(rnd.randint(5, 400) * 10)])
        if r > 0.4 and isinstance(row["cantidad"], int) and row["cantidad"] > 0:
            row["total"] = rnd.randint(5, 400) * 10 * row["cantidad"]
        c = rnd.choice(clientes)
        if c:
            row["cliente"] = c
        ventas.append({k: v for k, v in row.items() if v is not None})
    return productos, ventas


class TestDiferencial:
    @pytest.mark.parametrize("seed", range(25))
    async def test_coincide_con_el_oraculo_pandas(self, backend, seed):
        from decimal import Decimal
        from tests import insights_oracle as oracle

        productos, ventas = _random_case(seed)
        await load(backend, productos, ventas)
        result = await run()
        exp = oracle.compute(productos, ventas)
        if exp["period"] is None:
            assert result["period"] is None
            return
        assert result["period"] == {"from": exp["period"][0].isoformat(), "to": exp["period"][1].isoformat(),
                                    "days": exp["period"][2]}

        def money(x):
            return oracle.round_half_up(x)

        by_id = {i["id"]: i for i in result["items"]}
        if "capital_inventario" in by_id:
            m = metrics(by_id["capital_inventario"])
            assert m["Mercancía a costo"] == money(exp["merchandise"])
            assert m["Vendido en el periodo"] == money(exp["revenue"])
            if exp["months_inv"] is not None:
                assert m["Meses de inventario"] == float(
                    (Decimal(exp["months_inv"].numerator) / Decimal(exp["months_inv"].denominator)).quantize(
                        Decimal("0.1"), rounding="ROUND_HALF_UP"))
        if exp["stars"]:
            m = metrics(by_id["productos_estrella"])
            assert m["Utilidad total"] == money(exp["profit_total"])
            assert m["Utilidad de los productos estrella"] == money(sum(v for _n, v in exp["stars"]))
            for name, _v in exp["stars"]:
                assert oracle.key_of(name) in oracle.key_of(by_id["productos_estrella"]["sentence"])
        else:
            assert "productos_estrella" not in by_id
        if "reposicion" in by_id:
            m = metrics(by_id["reposicion"])
            assert m["Productos por agotarse"] == len(exp["restock"])
            if exp["restock"]:
                assert m["Días que le quedan"] == (int(exp["restock"][0][1]) if exp["restock"][0][1] > 0 else 0)
        if "clientes_concentracion" in by_id:
            m = metrics(by_id["clientes_concentracion"])
            assert m["Clientes distintos"] == exp["clients_n"]
            assert abs(m["Los 3 mejores clientes"] - float(exp["client_top3"]) * 100) <= 0.051
            assert abs(m["El mejor cliente"] - float(exp["client_first"]) * 100) <= 0.051
        else:
            assert exp["client_top3"] is None
        if "sin_movimiento" in by_id:
            m = metrics(by_id["sin_movimiento"])
            if exp["parked_n"]:
                assert m["Productos sin movimiento"] == exp["parked_n"]
                assert m["Plata parada"] == money(exp["parked_money"])
            else:
                assert m["Productos sin movimiento"] == 0
        if "margen_bajo" in by_id:
            m = metrics(by_id["margen_bajo"])
            assert m["Productos con margen bajo"] == exp["margin_flagged_n"]
            if exp["margin_flagged_n"]:
                assert m["Productos vendidos con pérdida"] == exp["margin_losing_n"]
                if exp["margin_losing_n"]:
                    assert m["Pérdida en ventas bajo el costo"] == money(exp["margin_loss"])
