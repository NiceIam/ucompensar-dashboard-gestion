"""Paso determinista del agente de esquema (schema_understanding) — PI0320251.

Valores a MANO: hojas con encabezados en espanol, ingles, abreviaturas colombianas, genericos y con tildes/espacios
raros. Verifica tipo de hoja, rol de cada columna y si la confianza es lo bastante alta para NO llamar al modelo.
"""

import warnings

import pandas as pd

from app.services import intake_service as intake
from app.services import schema_understanding as su


def understand(data: dict, file_name=None, sheet_name=None):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        prep = intake.prepare_sheet(pd.DataFrame(data))
    return su.understand_deterministic(prep.profiles, file_name=file_name, sheet_name=sheet_name)


def roles(u):
    return [c.role for c in u.columns]


class TestEspanol:
    def test_ventas_completas_es_clara(self):
        u = understand({"Fecha": ["2026-05-02", "2026-05-03"], "Producto": ["Gasas", "Jeringas"], "Cantidad": [3, 2],
                        "Precio Unitario": [1500, 800], "Total": [4500, 1600], "Cliente": ["Ana", "Luis"]})
        assert u.kind == "ventas" and u.clear
        assert roles(u) == ["fecha", "producto", "cantidad", "precio_unitario", "total", "cliente"]
        assert u.kind_confidence >= 0.9

    def test_productos_con_costo_y_existencias(self):
        u = understand({"Nombre": ["Gasas", "Jeringas"], "Vlr Compra": [900, 500], "Existencias": [10, 20],
                        "Precio Venta": [1500, 800]})
        assert u.kind == "productos" and u.clear
        assert roles(u) == ["producto_nombre", "costo_unitario", "stock", "precio_venta"]

    def test_compras_con_proveedor(self):
        u = understand({"Fecha": ["2026-05-02"], "Proveedor": ["Distri"], "Producto": ["Gasas"], "Cantidad": [100],
                        "Costo Unitario": [900], "Total": [90000]})
        assert u.kind == "compras" and u.clear
        assert roles(u) == ["fecha", "proveedor", "producto", "cantidad", "costo_unitario", "total"]

    def test_cuentas_por_cobrar(self):
        u = understand({"Cliente": ["Ana"], "Saldo": [120000], "Fecha Vencimiento": ["2026-06-01"],
                        "Estado": ["Pendiente"]})
        assert u.kind == "cuentas_por_cobrar" and u.clear
        assert roles(u) == ["cliente", "valor", "fecha_vencimiento", "estado"]

    def test_movimientos_de_inventario(self):
        u = understand({"Fecha": ["2026-05-02"], "Producto": ["Gasas"], "Tipo Movimiento": ["Entrada"],
                        "Cantidad": [5]})
        assert u.kind == "movimientos_inventario" and u.clear

    def test_clientes_por_nombre_de_archivo(self):
        u = understand({"Nombre": ["Ana"], "Telefono": ["3105551234"], "Correo": ["a@b.co"]},
                       file_name="Mis Clientes 2026.xlsx")
        assert u.kind == "clientes" and roles(u) == ["nombre", "telefono", "email"]

    def test_clientes_o_proveedores_sin_pistas_no_es_claro(self):
        u = understand({"Nombre": ["Ana"], "Telefono": ["3105551234"], "Email": ["a@b.co"]})
        assert not u.clear                         # se parece a ambos: hay que preguntar o usar el modelo

    def test_proveedores_por_nombre_de_hoja(self):
        u = understand({"Nombre": ["Distri"], "Telefono": ["3105551234"], "Email": ["a@b.co"]}, sheet_name="Proveedores")
        assert u.kind == "proveedores"

    def test_tildes_mayusculas_y_espacios_raros(self):
        u = understand({"  FECHA de Venta ": ["2026-05-02"], "Descripción  del Producto": ["Gasas"],
                        "CANTIDAD": [3], "Valor   Total": [4500]})
        assert u.kind == "ventas" and roles(u) == ["fecha", "producto", "cantidad", "total"]


class TestIngles:
    def test_ventas_en_ingles(self):
        u = understand({"date": ["2026-05-02", "2026-05-03"], "product": ["Gasas", "Jeringas"], "qty": [3, 2],
                        "price": [1500, 800], "customer": ["Ana", "Luis"]})
        assert u.kind == "ventas" and u.clear
        assert roles(u) == ["fecha", "producto", "cantidad", "precio_unitario", "cliente"]

    def test_productos_en_ingles(self):
        u = understand({"name": ["Gasas", "Jeringas"], "cost": [900, 500], "stock": [10, 20], "price": [1500, 800]})
        assert u.kind == "productos" and u.clear
        assert roles(u) == ["producto_nombre", "costo_unitario", "stock", "precio_venta"]

    def test_abreviaturas_colombianas(self):
        u = understand({"Fec": ["02/05/2026", "03/05/2026"], "Descripcion": ["Gasas", "Jeringas"], "Cant": [3, 2],
                        "Vlr Unit": [1500, 800], "Vlr Total": [4500, 1600]})
        assert u.kind == "ventas" and u.clear
        assert roles(u) == ["fecha", "producto", "cantidad", "precio_unitario", "total"]


class TestGenericos:
    def test_columnas_c1_c2_no_dicen_nada(self):
        u = understand({"C1": ["2026-05-02", "2026-05-03"], "C2": ["Gasas", "Jeringas"], "C3": [3, 2],
                        "C4": [1500, 800]})
        assert u.kind == "otro" and not u.clear and set(roles(u)) == {"otro"}
        assert u.kind_confidence <= 0.4

    def test_datos_que_no_son_del_negocio_quedan_como_otro(self):
        u = understand({"Nombre": ["Ana"], "Cargo": ["Cajera"], "Salario": [1500000]})
        assert u.kind == "otro" and set(roles(u)) == {"otro"}

    def test_producto_y_cantidad_solos_es_ambiguo(self):
        u = understand({"Producto": ["Gasas"], "Cantidad": [10]})
        assert not u.clear and u.kind_confidence < 0.8

    def test_correo_se_reconoce_por_contenido_aunque_el_encabezado_no_diga_nada(self):
        u = understand({"Nombre": ["Ana", "Luis"], "Contacto": ["Ana", "Luis"], "X": ["a@b.co", "l@c.co"]},
                       file_name="clientes.csv")
        assert u.kind == "clientes" and roles(u)[2] == "email"


class TestSeparaTipos:
    def test_inventario_no_se_confunde_con_ventas(self):
        u = understand({"Producto": ["Gasas"], "Cantidad": [10], "Costo": [900]}, file_name="inventario.csv")
        assert u.kind == "productos" and roles(u) == ["producto_nombre", "stock", "costo_unitario"]

    def test_con_fecha_y_cliente_no_es_lista_de_productos(self):
        u = understand({"Fecha": ["2026-05-02"], "Producto": ["Gasas"], "Cantidad": [1], "Precio": [900],
                        "Cliente": ["Ana"]})
        assert u.kind == "ventas"

    def test_proveedor_sin_cliente_es_compra_no_venta(self):
        u = understand({"Fecha": ["2026-05-02"], "Producto": ["Gasas"], "Cantidad": [1], "Total": [900],
                        "Proveedor": ["Distri"], "Costo": [900]})
        assert u.kind == "compras"

    def test_ventas_con_fecha_y_total_no_son_cuentas_por_cobrar(self):
        u = understand({"Fecha": ["2026-05-02"], "Producto": ["Gasas"], "Cantidad": [1], "Total": [900],
                        "Cliente": ["Ana"]})
        assert u.kind == "ventas"

    def test_nombre_de_archivo_confirma_un_tipo_incompleto(self):
        sin_hint = understand({"Fecha": ["2026-05-02"], "Producto": ["Gasas"], "Total": [900]})
        con_hint = understand({"Fecha": ["2026-05-02"], "Producto": ["Gasas"], "Total": [900]}, file_name="ventas_mayo.csv")
        assert sin_hint.kind == "otro" and con_hint.kind == "ventas"

    def test_contenido_desmiente_al_encabezado(self):
        # "fecha" con texto libre y "total" con nombres: no se creen
        u = understand({"Fecha": ["ayer", "hoy"], "Producto": ["Gasas", "Jeringas"], "Cantidad": [1, 2],
                        "Total": ["Ana", "Luis"]})
        assert not u.clear


class TestNormalizarHoja:
    def test_encabezado_real_debajo_de_un_titulo(self):
        raw = pd.DataFrame([["REPORTE DE VENTAS OCTUBRE", None, None, None],
                            [None, None, None, None],
                            ["Fecha", "Producto", "Cantidad", "Total"],
                            ["2026-10-02", "Gasas", 3, 4500]],
                           columns=["Unnamed: 0", "Unnamed: 1", "Unnamed: 2", "Unnamed: 3"])
        df = intake.normalize_frame(raw)
        assert list(df.columns) == ["Fecha", "Producto", "Cantidad", "Total"] and len(df) == 1

    def test_quita_filas_y_columnas_vacias(self):
        raw = pd.DataFrame({"a": [1, None, 3], "Unnamed: 1": [None, None, None]})
        raw.loc[1] = [None, None]
        df = intake.normalize_frame(raw)
        assert list(df.columns) == ["a"] and len(df) == 2

    def test_hoja_normal_no_se_toca(self):
        raw = pd.DataFrame({"a": [1], "b": [2]})
        assert intake.normalize_frame(raw).equals(raw)


class TestFirmaYNombres:
    def test_pistas_del_nombre(self):
        assert su.name_hint_kinds("Compras 2026", None) == {"compras"}
        assert su.name_hint_kinds(None, "cartera_octubre.xlsx") == {"cuentas_por_cobrar"}
        assert su.name_hint_kinds("Hoja1", "datos.csv") == set()

    def test_tipo_de_una_tabla_guardada_solo_por_nombres(self):
        assert su.kind_of_names(["fecha", "producto", "cantidad", "precio_unitario", "total", "cliente",
                                 "metodo_pago"])[0] == "ventas"
        assert su.kind_of_names(["nombre", "cargo", "salario", "departamento"])[0] == "otro"
        assert su.kind_of_names([])[0] == "otro"
