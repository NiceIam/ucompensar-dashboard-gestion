import { describe, expect, test } from "vitest"
import {
  buildSummaryText,
  formatMetric,
  joinNames,
  normalizeInsights,
  parseIsoDate,
  periodLabel,
  prettyTable,
  sortInsights,
  topInsights,
  whatsappUrl,
} from "./insights"
import type { Insight, InsightSeverity } from "@/types/insights"

/** Los formateadores usan espacios que no se parten; en las pruebas se leen como espacios normales. */
const plain = (s: string) => s.replace(/[  ]/g, " ")

function insight(id: string, severity: InsightSeverity, sentence = `frase ${id}`): Insight {
  return {
    id,
    kind: "money",
    severity,
    title: `titulo ${id}`,
    sentence,
    metrics: [],
    how: { steps: [], tables: [], rows_used: 0, notes: [] },
  }
}

describe("formato de cifras según su unidad", () => {
  test("dinero: millones compactos y miles completos", () => {
    expect(plain(formatMetric({ value: 47_620_000, unit: "money" }))).toBe("$47,6 M")
    expect(plain(formatMetric({ value: 10_234_700, unit: "money" }))).toBe("$10,2 M")
    expect(plain(formatMetric({ value: 360_000, unit: "money" }))).toBe("$360.000")
    expect(plain(formatMetric({ value: 850, unit: "money" }))).toBe("$850")
    expect(plain(formatMetric({ value: 3_200_000_000, unit: "money" }))).toBe("$3.200 M")
    expect(plain(formatMetric({ value: -1_500_000, unit: "money" }))).toBe("-$1,5 M")
  })

  test("porcentaje en escala 0-100 con coma decimal", () => {
    expect(plain(formatMetric({ value: 12, unit: "percent" }))).toBe("12 %")
    expect(plain(formatMetric({ value: 12.5, unit: "percent" }))).toBe("12,5 %")
    expect(plain(formatMetric({ value: 3.2, unit: "percent" }))).toBe("3,2 %")
  })

  test("conteos con puntos de miles", () => {
    expect(formatMetric({ value: 1234, unit: "count" })).toBe("1.234")
    expect(formatMetric({ value: 3, unit: "count" })).toBe("3")
  })

  test("días y meses con singular y plural", () => {
    expect(plain(formatMetric({ value: 12, unit: "days" }))).toBe("12 días")
    expect(plain(formatMetric({ value: 1, unit: "days" }))).toBe("1 día")
    expect(plain(formatMetric({ value: 0.2, unit: "days" }))).toBe("menos de 1 día")
    expect(plain(formatMetric({ value: 20.1, unit: "months" }))).toBe("20 meses")
    expect(plain(formatMetric({ value: 1.5, unit: "months" }))).toBe("1,5 meses")
    expect(plain(formatMetric({ value: 1, unit: "months" }))).toBe("1 mes")
  })

  test("texto pasa tal cual y un valor roto no muestra NaN", () => {
    expect(formatMetric({ value: "Tornillo 3/8", unit: "text" })).toBe("Tornillo 3/8")
    expect(formatMetric({ value: Number.NaN, unit: "money" })).toBe("—")
    expect(formatMetric({ value: "abc", unit: "count" })).toBe("—")
  })
})

describe("orden y selección de hallazgos", () => {
  const items = [
    insight("a", "info"),
    insight("b", "important"),
    insight("c", "attention"),
    insight("d", "important"),
    insight("e", "info"),
  ]

  test("severidad de mayor a menor y, a igual severidad, el orden del servidor", () => {
    expect(sortInsights(items).map((i) => i.id)).toEqual(["b", "d", "c", "a", "e"])
  })

  test("no modifica la lista original", () => {
    const copy = [...items]
    sortInsights(items)
    expect(items).toEqual(copy)
  })

  test("los 3 más importantes para el inicio", () => {
    expect(topInsights(items).map((i) => i.id)).toEqual(["b", "d", "c"])
    expect(topInsights(items.slice(0, 2)).map((i) => i.id)).toEqual(["b", "a"])
    expect(topInsights([])).toEqual([])
  })
})

describe("periodo y fechas", () => {
  test("una fecha ISO se lee como día local, no se corre un día por la zona horaria", () => {
    const d = parseIsoDate("2025-07-02")!
    expect([d.getFullYear(), d.getMonth(), d.getDate()]).toEqual([2025, 6, 2])
    expect(parseIsoDate("no es fecha")).toBeNull()
  })

  test("frase del periodo de ventas", () => {
    expect(periodLabel({ from: "2025-07-02", to: "2025-10-08", days: 98 })).toBe(
      "Ventas del 2 de julio al 8 de octubre de 2025"
    )
    expect(periodLabel(null)).toBeNull()
    expect(periodLabel({ from: "x", to: "y", days: 0 })).toBeNull()
  })

  test("nombres de hojas legibles", () => {
    expect(prettyTable("productos")).toBe("Productos")
    expect(prettyTable("ventas_2025")).toBe("Ventas 2025")
    expect(joinNames(["Productos", "Ventas"])).toBe("Productos y Ventas")
    expect(joinNames(["A", "B", "C"])).toBe("A, B y C")
    expect(joinNames([])).toBe("")
  })
})

describe("compartir el resumen", () => {
  test("el enlace de WhatsApp lleva el texto codificado y no un número", () => {
    const url = whatsappUrl("Resumen\n• Tienes $47,6 M & más")
    expect(url.startsWith("https://wa.me/?text=")).toBe(true)
    expect(url).toContain("%0A")
    expect(url).toContain("%24")
    expect(url).toContain("%26")
    expect(decodeURIComponent(url.split("?text=")[1])).toBe("Resumen\n• Tienes $47,6 M & más")
  })

  test("el texto a copiar es el del servidor, sin espacios sobrantes", () => {
    expect(buildSummaryText({ items: [], generated_at: "2026-10-19T14:05:00Z", summary_text: "  Hola\n• uno  " })).toBe(
      "Hola\n• uno"
    )
  })

  test("si el servidor no lo manda, se arma con las frases ordenadas por importancia", () => {
    const text = buildSummaryText({
      generated_at: "2026-10-19T14:05:00",
      summary_text: null,
      items: [insight("a", "info", "Frase A"), insight("b", "important", "Frase B")],
    })
    expect(text).toBe("Resumen de tu negocio (lunes 19 de octubre)\n• Frase B\n• Frase A")
  })
})

describe("normalizar la respuesta", () => {
  test("rellena lo que falte sin romper", () => {
    const out = normalizeInsights({ items: [{ id: "x", title: "t" } as Insight] })
    expect(out.missing).toEqual([])
    expect(out.period).toBeNull()
    expect(out.items[0].metrics).toEqual([])
    expect(out.items[0].how).toEqual({ steps: [], tables: [], rows_used: 0, notes: [] })
    expect(normalizeInsights(null).items).toEqual([])
  })
})
