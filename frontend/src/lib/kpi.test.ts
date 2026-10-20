import { describe, expect, test } from "vitest"
import { formatKpiValue, kpiUnit } from "./kpi"

describe("unidad de los KPI del tablero", () => {
  test("un conteo de filas NO se muestra como dinero aunque la etiqueta diga «Ventas»", () => {
    // Forma real que manda hoy el backend (dashboard_script_service.py).
    const kpi = { label: "Total Ventas", value: 40, icon: "Database" }
    expect(kpiUnit(kpi)).toBe("count")
    expect(formatKpiValue(kpi)).toBe("40")
    expect(formatKpiValue(kpi)).not.toContain("$")
  })

  test("registros totales con icono de tendencia también son cantidad", () => {
    expect(formatKpiValue({ label: "Registros totales", value: 1584, icon: "TrendingUp" })).toBe("1.584")
  })

  test("entero sin pista y con etiqueta monetaria: cantidad, no pesos", () => {
    expect(kpiUnit({ label: "Valor total", value: 12, icon: "" })).toBe("count")
  })

  test("icono de dinero -> pesos", () => {
    expect(kpiUnit({ label: "Ingresos", value: 48_300_000, icon: "DollarSign" })).toBe("money")
    expect(formatKpiValue({ label: "Ingresos", value: 48_300_000, icon: "DollarSign" })).toMatch(/^\$\s?48,3\s?M$/)
  })

  test("columna de origen de dinero -> pesos", () => {
    expect(kpiUnit({ label: "Suma", value: 9500, icon: "Hash", column: "precio_unitario" })).toBe("money")
    expect(kpiUnit({ label: "Suma", value: 9500, icon: "Hash", column: "cantidad" })).toBe("count")
  })

  test("la unidad explícita del backend manda sobre todo lo demás", () => {
    expect(kpiUnit({ label: "Total Ventas", value: 40, icon: "DollarSign", unit: "count" })).toBe("count")
    expect(kpiUnit({ label: "Pedidos", value: 40, icon: "Database", unit: "money" })).toBe("money")
  })

  test("decimal sin pista -> número; no finito -> raya", () => {
    expect(kpiUnit({ label: "Promedio", value: 3.75 })).toBe("number")
    expect(formatKpiValue({ label: "Promedio", value: Number.NaN })).toBe("—")
  })

  test("una cifra que no se pudo calcular (null) se muestra como raya y no rompe la unidad", () => {
    expect(formatKpiValue({ label: "Suma de total", value: null, unit: "money" })).toBe("—")
    expect(kpiUnit({ label: "Suma de total", value: null, unit: "money" })).toBe("money")
    expect(kpiUnit({ label: "Suma", value: null })).toBe("number")
  })
})

describe("cartera sin palabra de dinero en el nombre", () => {
  test("«Suma de cuánto debe» sale en pesos por su columna de origen, aunque la unidad no llegue", () => {
    expect(kpiUnit({ label: "Suma de cuánto debe", value: 5_600_000, icon: "TrendingUp", column: "cuánto_debe" })).toBe("money")
    expect(formatKpiValue({ label: "Suma de cuánto debe", value: 5_600_000, icon: "TrendingUp", column: "cuánto_debe" })).toMatch(/^\$.5,6.M$/)
  })
})
