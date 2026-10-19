import { describe, expect, test } from "vitest"
import {
  buildSummaryText,
  formatMetric,
  joinNames,
  normalizeInsights,
  parseIsoDate,
  periodLabel,
  prettyTable,
  splitCommonNotes,
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

describe("selección de hallazgos: el orden lo manda el servidor", () => {
  const items = [
    insight("a", "info"),
    insight("b", "important"),
    insight("c", "attention"),
    insight("d", "important"),
    insight("e", "info"),
  ]

  test("el inicio muestra los 3 primeros tal como llegan, sin reordenar por severidad", () => {
    expect(topInsights(items).map((i) => i.id)).toEqual(["a", "b", "c"])
    expect(topInsights(items, 2).map((i) => i.id)).toEqual(["a", "b"])
    expect(topInsights([])).toEqual([])
  })

  test("no modifica la lista original", () => {
    const copy = [...items]
    topInsights(items)
    expect(items).toEqual(copy)
  })
})

describe("avisos repetidos entre hallazgos", () => {
  const withNotes = (id: string, notes: string[]): Insight => ({
    ...insight(id, "attention"),
    how: { steps: [], tables: [], rows_used: 0, notes },
  })
  const LAST_SALE = "Tu última venta registrada es del 8 de octubre de 2025: si ya vendiste después, sube el archivo actualizado."

  test("un aviso idéntico en 2 o más hallazgos sale una vez y se quita de las tarjetas", () => {
    const { common, items } = splitCommonNotes([
      withNotes("a", [LAST_SALE, "Propio de A"]),
      withNotes("b", [LAST_SALE]),
      withNotes("c", [LAST_SALE, "Propio de C"]),
    ])
    expect(common).toEqual([LAST_SALE])
    expect(items.map((i) => i.how.notes)).toEqual([["Propio de A"], [], ["Propio de C"]])
  })

  test("con un solo hallazgo el aviso se queda en su tarjeta", () => {
    const one = [withNotes("a", [LAST_SALE])]
    const out = splitCommonNotes(one)
    expect(out.common).toEqual([])
    expect(out.items[0].how.notes).toEqual([LAST_SALE])
  })

  test("avisos distintos no se tocan", () => {
    const list = [withNotes("a", ["Uno"]), withNotes("b", ["Dos"])]
    const out = splitCommonNotes(list)
    expect(out.common).toEqual([])
    expect(out.items).toBe(list)
  })

  test("orden estable: los comunes salen en el orden de su primera aparición", () => {
    const { common } = splitCommonNotes([
      withNotes("a", ["Zeta", "Alfa"]),
      withNotes("b", ["Alfa", "Zeta", "Solo B"]),
    ])
    expect(common).toEqual(["Zeta", "Alfa"])
  })

  test("espacios de más no esconden un aviso repetido; un aviso repetido dentro de UN hallazgo no cuenta", () => {
    const { common } = splitCommonNotes([withNotes("a", ["Mismo  aviso", "Mismo aviso"]), withNotes("b", ["Otro"])])
    expect(common).toEqual([])
    const out = splitCommonNotes([withNotes("a", ["Mismo  aviso"]), withNotes("b", [" Mismo aviso "])])
    expect(out.common).toEqual(["Mismo aviso"])
  })

  test("no modifica los hallazgos originales", () => {
    const a = withNotes("a", [LAST_SALE])
    splitCommonNotes([a, withNotes("b", [LAST_SALE])])
    expect(a.how.notes).toEqual([LAST_SALE])
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

  test("si el servidor no lo manda, se arma con las frases en el orden en que llegan", () => {
    const text = buildSummaryText({
      generated_at: "2026-10-19T14:05:00",
      summary_text: null,
      items: [insight("a", "info", "Frase A"), insight("b", "important", "Frase B")],
    })
    expect(text).toBe("Resumen de tu negocio (lunes 19 de octubre)\n• Frase A\n• Frase B")
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
