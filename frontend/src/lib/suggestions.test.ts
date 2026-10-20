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
    // El nombre limpio perdió la pista, pero la etiqueta original la conserva.
    expect(columnKind({ name: "col_1", label: "#", type: "integer" })).toBe("id")
    expect(columnKind({ name: "index", label: "Index", type: "integer" })).toBe("id")
  })

  test("detección de códigos y dinero", () => {
    expect(isIdLike("numero_factura")).toBe(true)
    expect(isIdLike("valor_total")).toBe(false)
    // Índices de hojas exportadas, sin importar mayúsculas (salieron como "medida" en el demo real).
    for (const name of ["Index", "index", "INDEX", "id", "ID", "cliente_id", "clienteId", "#", "N°", "Nº", "Índice", "Unnamed: 0", "idx"]) {
      expect(isIdLike(name), name).toBe(true)
    }
    // Un índice como métrica de negocio sigue siendo medida.
    expect(isIdLike("indice_satisfaccion")).toBe(false)
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

  test("una columna de índice nunca se usa como medida", () => {
    const conIndice = {
      name: "Ventas",
      rowCount: 300,
      columns: [
        { name: "Index", type: "integer" },
        { name: "fecha", type: "date" },
        { name: "region", type: "text" },
        { name: "cantidad", type: "integer" },
      ],
    }
    const qs = questionsForTable(conIndice)
    expect(qs.join(" ")).not.toMatch(/index/i)
    expect(qs[0]).toBe("¿Cómo cambia la cantidad mes a mes?")
    const soloIndice = { ...conIndice, columns: [{ name: "Index", type: "integer" }, { name: "#", type: "integer" }, { name: "fecha", type: "date" }] }
    expect(questionsForTable(soloIndice).join(" ")).not.toMatch(/index|«#»/i)
  })

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

describe("nombres legibles de encabezados crudos", () => {
  test.each([
    ["vr.total", "Valor total"],
    ["Vr.Total", "Valor total"],
    ["fec", "Fecha"],
    ["p.unit", "Precio unitario"],
    ["Cant", "Cantidad"],
    ["qty", "Cantidad"],
    ["Item", "Producto"],
    ["Sell Price", "Precio de venta"],
    ["¿Cuánto debe?", "Cuánto debe"],
    ["cuánto_debe", "Cuánto debe"],
  ])("%s -> %s", (raw, expected) => {
    expect(humanizeName(raw)).toBe(expected)
  })

  test("las abreviaturas también ayudan a reconocer dinero y categorías", () => {
    expect(isMoneyLike("vr.total")).toBe(true)
    expect(isMoneyLike("cuánto_debe")).toBe(true)
    expect(isMoneyLike("fiados")).toBe(true)
    expect(isMoneyLike("cant")).toBe(false)
    expect(columnKind({ name: "cuánto_debe", type: "number" })).toBe("money")
  })
})
