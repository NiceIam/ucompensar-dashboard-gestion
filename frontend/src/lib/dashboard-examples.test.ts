import { describe, expect, test } from "vitest"
import { dashboardRequests, dashboardRequestsForTable } from "./dashboard-examples"

const ventas = {
  name: "ventas",
  rowCount: 120,
  columns: [
    { name: "fecha", type: "date" },
    { name: "producto", type: "text" },
    { name: "total", type: "number" },
    { name: "factura", type: "text" },
  ],
}
const clientes = {
  name: "clientes",
  rowCount: 40,
  columns: [
    { name: "nombre", type: "text" },
    { name: "ciudad", type: "text" },
    { name: "telefono", type: "integer" },
  ],
}

describe("pedidos de ejemplo para tableros (plantillas locales, sin IA)", () => {
  test("fecha + medida da una serie por mes con la frase correcta", () => {
    const [first] = dashboardRequestsForTable(ventas)
    expect(first).toBe("Quiero un tablero con el total mes a mes")
  })

  test("medida + categoría da el pedido por categoría con columnas reales", () => {
    expect(dashboardRequestsForTable(ventas)).toContain("Quiero un tablero con el total por producto")
  })

  test("nunca usa un código o teléfono como medida ni como categoría", () => {
    const all = dashboardRequestsForTable(clientes).join(" ")
    expect(all).not.toMatch(/tel[eé]fono|factura/i)
    expect(all).toContain("por ciudad")
  })

  test("hasta 3 pedidos variados, alternando entre hojas y sin repetir", () => {
    const out = dashboardRequests([clientes, ventas], 3)
    expect(out).toHaveLength(3)
    expect(new Set(out).size).toBe(3)
    expect(out[0]).toContain("total mes a mes") // la hoja con más filas primero
  })

  test("sin hojas con datos no inventa pedidos", () => {
    expect(dashboardRequests([], 3)).toEqual([])
    expect(dashboardRequests([{ ...ventas, rowCount: 0 }], 3)).toEqual([])
  })
})
