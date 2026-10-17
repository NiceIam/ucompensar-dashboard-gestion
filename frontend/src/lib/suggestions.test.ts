import { describe, expect, test } from "vitest"
import { columnKind, columnLabel, humanizeName, isIdLike, isMoneyLike, pickCategory } from "./data-vocabulary"
import { measurePhrase, questionsForTable, suggestQuestions } from "./suggestions"

describe("vocabulario de datos", () => {
  test("humanizeName vuelve legibles los nombres técnicos", () => {
    expect(humanizeName("precio_unitario")).toBe("Precio unitario")
    expect(humanizeName("fechaVenta")).toBe("Fecha venta")
    expect(humanizeName("valor_iva")).toBe("Valor IVA")
    expect(humanizeName("nombre_2")).toBe("Nombre 2")
    expect(humanizeName("Región")).toBe("Región")
    expect(humanizeName("region")).toBe("Región")
    expect(humanizeName("cotizacion")).toBe("Cotización")
    expect(humanizeName("cotizaciones")).toBe("Cotizaciones")
  })

  test("columnLabel prefiere la etiqueta amable", () => {
    expect(columnLabel({ name: "precio_venta", label: "Precio de venta" })).toBe("Precio de venta")
    expect(columnLabel({ name: "precio_venta", label: "precio_venta" })).toBe("Precio venta")
  })

  test("columnKind traduce tipos técnicos a clases de negocio", () => {
    expect(columnKind({ name: "fecha", type: "date" })).toBe("date")
    expect(columnKind({ name: "total", type: "number" })).toBe("money")
    expect(columnKind({ name: "cantidad", type: "integer" })).toBe("number")
    expect(columnKind({ name: "telefono", type: "integer" })).toBe("id")
    expect(columnKind({ name: "nit", type: "text" })).toBe("id")
    expect(columnKind({ name: "pagado", type: "boolean" })).toBe("boolean")
    expect(columnKind({ name: "region", type: "varchar" })).toBe("text")
  })

  test("detección de códigos y dinero", () => {
    expect(isIdLike("numero_factura")).toBe(true)
    expect(isIdLike("valor_total")).toBe(false)
    expect(isMoneyLike("precioVenta")).toBe(true)
    expect(isMoneyLike("cantidad")).toBe(false)
  })

  test("pickCategory prefiere columnas de agrupación y descarta texto libre o únicos", () => {
    const cols = [
      { name: "descripcion", type: "text" },
      { name: "cliente_nombre", type: "text" },
      { name: "region", type: "text" },
    ]
    expect(pickCategory(cols)?.name).toBe("region")
    expect(pickCategory([{ name: "region", type: "text", distinct: 300 }], 300)).toBeUndefined()
    expect(pickCategory([{ name: "observaciones", type: "text" }])).toBeUndefined()
  })
})

describe("preguntas sugeridas", () => {
  const ventas = {
    name: "Ventas",
    rowCount: 300,
    columns: [
      { name: "fecha", type: "date" },
      { name: "producto", type: "text" },
      { name: "region", type: "text" },
      { name: "total", type: "number" },
    ],
  }

  test("fecha + número -> evolución mes a mes con el artículo correcto", () => {
    expect(questionsForTable(ventas)[0]).toBe("¿Cómo cambia el total mes a mes?")
    const unidades = { ...ventas, columns: [{ name: "fecha", type: "date" }, { name: "unidades", type: "integer" }] }
    expect(questionsForTable(unidades)[0]).toBe("¿Cómo cambian las unidades mes a mes?")
  })

  test("categoría + número -> comparación por categoría", () => {
    expect(questionsForTable(ventas)).toContain("Muéstrame el total por región")
  })

  test("medidas desconocidas van entre comillas, nunca con un artículo inventado", () => {
    expect(measurePhrase({ name: "puntaje" }).phrase).toBe("«puntaje»")
    expect(measurePhrase({ name: "precio_unitario" }).phrase).toBe("el precio unitario")
  })

  test("solo texto -> qué aparece más", () => {
    const clientes = { name: "clientes", rowCount: 40, columns: [{ name: "ciudad", type: "text" }, { name: "email", type: "text" }] }
    expect(questionsForTable(clientes)[0]).toBe("¿Qué ciudad aparece más en Clientes?")
  })

  test("número sin fecha ni categoría usa 'del' bien contraído", () => {
    const t = { name: "Caja", rowCount: 10, columns: [{ name: "total", type: "number" }] }
    expect(questionsForTable(t)[0]).toBe("Dame el total, el promedio y el máximo del total")
  })

  test("siempre hay un resumen como último recurso", () => {
    const t = { name: "notas_internas", rowCount: 3, columns: [{ name: "observaciones", type: "text" }] }
    expect(questionsForTable(t)).toEqual(["Hazme un resumen de Notas internas"])
  })

  test("suggestQuestions alterna entre tablas y respeta el máximo", () => {
    const clientes = { name: "Clientes", rowCount: 40, columns: [{ name: "ciudad", type: "text" }] }
    const vacia = { name: "Proveedores", rowCount: 0, columns: [{ name: "ciudad", type: "text" }] }
    const qs = suggestQuestions([clientes, ventas, vacia], 3)
    expect(qs).toHaveLength(3)
    expect(qs[0]).toBe("¿Cómo cambia el total mes a mes?")
    expect(qs[1]).toBe("¿Qué ciudad aparece más en Clientes?")
    expect(qs.some((q) => q.includes("Proveedores"))).toBe(false)
  })

  test("sin tablas con datos no se sugiere nada", () => {
    expect(suggestQuestions([])).toEqual([])
    expect(suggestQuestions([{ name: "Ventas", rowCount: 0, columns: [{ name: "total", type: "number" }] }])).toEqual([])
  })
})
