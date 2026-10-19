"""Modelo base del negocio (intake_ontology): firma de estructura, metadata sin migracion y listas blancas — PI0320251."""

import json

import pytest

from app.services import intake_ontology as onto


class TestSignature:
    def test_ignora_mayusculas_tildes_espacios_y_orden(self):
        a = onto.signature(["Fecha", "Descripción", "Vlr  Total"])
        b = onto.signature(["vlr total", "DESCRIPCION", " fecha "])
        assert a == b

    def test_encabezados_distintos_firmas_distintas(self):
        assert onto.signature(["fecha", "total"]) != onto.signature(["fecha", "totales"])

    def test_columnas_repetidas_cuentan(self):
        assert onto.signature(["a", "a"]) != onto.signature(["a"])

    def test_largo_fijo_hexadecimal(self):
        sig = onto.signature(["x"])
        assert len(sig) == 24 and int(sig, 16) >= 0


class TestListasBlancas:
    def test_los_ocho_tipos_pedidos(self):
        assert set(onto.KINDS) == {"productos", "ventas", "compras", "cuentas_por_cobrar", "movimientos_inventario",
                                   "clientes", "proveedores", "otro"}

    def test_roles_por_tipo_exactos(self):
        assert onto.ROLES_BY_KIND["productos"] == ("producto_nombre", "producto_codigo", "categoria", "costo_unitario",
                                                   "precio_venta", "stock", "proveedor")
        assert onto.ROLES_BY_KIND["ventas"] == ("fecha", "producto", "cantidad", "precio_unitario", "total", "cliente",
                                                "metodo_pago")
        assert onto.ROLES_BY_KIND["compras"] == ("fecha", "producto", "cantidad", "costo_unitario", "total",
                                                 "proveedor", "documento")
        assert onto.ROLES_BY_KIND["cuentas_por_cobrar"] == ("cliente", "valor", "fecha_emision", "fecha_vencimiento",
                                                            "estado")
        assert onto.ROLES_BY_KIND["movimientos_inventario"] == ("fecha", "producto", "tipo_movimiento", "cantidad")
        assert onto.ROLES_BY_KIND["clientes"] == onto.ROLES_BY_KIND["proveedores"] == (
            "nombre", "contacto", "telefono", "email")

    @pytest.mark.parametrize("kind,role,ok", [
        ("ventas", "fecha", True), ("ventas", "costo_unitario", False), ("compras", "costo_unitario", True),
        ("ventas", "otro", True), ("otro", "fecha", False), ("otro", "otro", True), ("inventado", "fecha", False),
        ("ventas", None, False), (None, "fecha", False), ("ventas", 7, False), ("ventas", "fecha; DROP", False),
    ])
    def test_is_valid_role(self, kind, role, ok):
        assert onto.is_valid_role(kind, role) is ok

    def test_todo_rol_tiene_explicacion_en_espanol_sencillo(self):
        for kind, roles in onto.ROLES_BY_KIND.items():
            for r in roles:
                title, explain = onto.role_titles(kind, r)
                assert title and explain and (title, explain) != onto.OTHER_EXPLAIN, (kind, r)

    def test_allowed_roles_incluye_otro_al_final(self):
        opts = onto.allowed_roles("compras")
        assert [o["role"] for o in opts] == list(onto.ROLES_BY_KIND["compras"]) + ["otro"]


class TestMetadata:
    COLS = [{"name": "fecha", "type": "date"}, {"name": "x", "type": "text", "role": "producto"}]

    def test_hoja_sin_metadata_es_compatible_hacia_atras(self):
        assert onto.read_sheet_meta(self.COLS) is None
        assert onto.column_roles(self.COLS) == {}

    def test_ida_y_vuelta_y_solo_la_primera_columna_lleva_la_hoja(self):
        meta = onto.make_sheet_meta("ventas", 0.93, "ai", "abc")
        cols = onto.with_sheet_meta(self.COLS, meta)
        assert "sheet" in cols[0] and "sheet" not in cols[1]
        got = onto.read_sheet_meta(json.dumps(cols))          # asyncpg devuelve jsonb como texto
        assert got["kind"] == "ventas" and got["mapping_source"] == "ai" and got["signature"] == "abc"
        assert got["kind_confidence"] == 0.93

    def test_reescribir_no_deja_metadata_duplicada(self):
        cols = onto.with_sheet_meta(self.COLS, onto.make_sheet_meta("ventas", 1, "ai", "a"))
        cols = onto.with_sheet_meta(cols, onto.make_sheet_meta("compras", 1, "user", "b"))
        assert sum("sheet" in c for c in cols) == 1
        assert onto.read_sheet_meta(cols)["kind"] == "compras"

    def test_tipo_invalido_en_la_bd_se_ignora(self):
        cols = [{"name": "a", "sheet": {"kind": "hackeo"}}]
        assert onto.read_sheet_meta(cols) is None

    def test_rol_fuera_de_la_lista_blanca_en_la_bd_se_ignora(self):
        cols = onto.with_sheet_meta(
            [{"name": "a", "role": "costo_unitario"}, {"name": "b", "role": "fecha"}, {"name": "c", "role": 5}],
            onto.make_sheet_meta("ventas", 1, "user", None))
        roles = onto.column_roles(cols)
        assert set(roles) == {"b"} and roles["b"]["role"] == "fecha"      # costo_unitario no existe en ventas

    def test_confianza_basura_queda_en_cero(self):
        cols = onto.with_sheet_meta([{"name": "a", "role": "fecha", "role_confidence": "alta"}],
                                    {"kind": "ventas", "kind_confidence": True})
        assert onto.column_roles(cols)["a"]["confidence"] == 0.0
        assert onto.read_sheet_meta(cols)["kind_confidence"] == 0.0

    def test_columns_definition_mal_formada(self):
        assert onto.parse_columns("{no json") == [] and onto.parse_columns(None) == [] and onto.parse_columns({}) == []


class TestClean:
    def test_clean_text_una_linea_sin_control_y_acotado(self):
        assert onto.clean_text("a\x00b\r\nc d   e", 50) == "a b c d e"
        assert onto.clean_text("x" * 100, 10) == "x" * 10
