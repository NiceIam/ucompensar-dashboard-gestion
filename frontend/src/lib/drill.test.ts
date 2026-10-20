import { describe, expect, test } from "vitest"
import { barWidth, drillAnnouncement, drillRequestFor, drillTarget, drillVariant, formatByUnit, pointLabel } from "./drill"
import { EMPTY_FILTERS } from "./dashboard-filters"
import type { DrillResponse, DrillRow } from "@/types/dashboard-filters"

describe("qué se pide al tocar un dato", () => {
  test("usa la clave EXACTA cuando el nombre se recortó, y el nombre si no", () => {
    expect(drillRequestFor({ name: "Grifería lavamanos monocont…", key: "Grifería lavamanos monocontrol cromo", value: 1 }, EMPTY_FILTERS)).toEqual({
      value: "Grifería lavamanos monocontrol cromo",
    })
    expect(drillRequestFor({ name: "Cemento", value: 1 }, EMPTY_FILTERS)).toEqual({ value: "Cemento" })
  })

  test("«(sin dato)» manda null y «Otros» manda other, nunca el texto visible", () => {
    expect(drillRequestFor({ name: "(sin dato)", value: 1, empty: true }, EMPTY_FILTERS)).toEqual({ value: null })
    expect(drillRequestFor({ name: "Otros (42)", value: 1, other: true }, EMPTY_FILTERS)).toEqual({ other: true })
  })

  test("agrega «Ver por» y los filtros activos del tablero", () => {
    const req = drillRequestFor(
      { name: "2026-09", value: 1 },
      { period: { preset: "last_month" }, where: [{ key: "cliente", values: ["Ana"] }] },
      "day(fecha)"
    )
    expect(req).toEqual({
      value: "2026-09",
      by: "day(fecha)",
      filters: { period: { preset: "last_month" }, where: [{ key: "cliente", values: ["Ana"] }] },
    })
  })

  test("otro dato es otro objetivo; cambiar «Ver por» o los filtros no lo es", () => {
    const a = drillRequestFor({ name: "A", value: 1 }, EMPTY_FILTERS)
    const b = drillRequestFor({ name: "B", value: 1 }, EMPTY_FILTERS)
    const aBy = drillRequestFor({ name: "A", value: 1 }, { period: { preset: "last_7" }, where: [] }, "cliente")
    expect(drillTarget("w", a)).not.toBe(drillTarget("w", b))
    expect(drillTarget("w", a)).toBe(drillTarget("w", aBy))
    expect(drillVariant(a)).not.toBe(drillVariant(aBy))
    expect(drillTarget("w1", a)).not.toBe(drillTarget("w2", a))
  })
})

// Los importes usan espacio que no se parte (NBSP): para comparar se pasan a espacio normal.
const plain = (text: string) => text.replace(/[  ]/g, " ")

describe("barras de proporción y textos", () => {
  const rows: DrillRow[] = [
    { name: "A", value: 600, share: 0.6 },
    { name: "B", value: 300, share: 0.3 },
    { name: "C", value: 100, share: 0.1 },
  ]

  test("si la medida se suma, la barra es la parte del total", () => {
    expect(barWidth(rows[0], rows, true)).toBeCloseTo(60)
    expect(barWidth(rows[2], rows, true)).toBeCloseTo(10)
  })

  test("si no se suma (promedio), la barra es frente al mayor", () => {
    const avg = rows.map((r) => ({ ...r, share: null }))
    expect(barWidth(avg[0], avg, false)).toBe(100)
    expect(barWidth(avg[1], avg, false)).toBeCloseTo(50)
  })

  test("valores raros no rompen el ancho", () => {
    expect(barWidth({ name: "x", value: -5, share: null }, rows, false)).toBe(0)
    expect(barWidth({ name: "x", value: Number.NaN, share: null }, rows, false)).toBe(0)
    expect(barWidth({ name: "x", value: 1, share: 7 }, rows, true)).toBe(100)
    expect(barWidth({ name: "x", value: 0, share: null }, [{ name: "x", value: 0, share: null }], false)).toBe(0)
  })

  test("formato por unidad y frase del dato", () => {
    expect(plain(formatByUnit(1_004_000, "money"))).toBe("$ 1.004.000")
    expect(plain(formatByUnit(1_004_000, "money", true))).toBe("$ 1 M")
    expect(formatByUnit(40, "count")).toBe("40")
    expect(plain(pointLabel({ name: "2026-09-15", value: 1_004_000 }, "money"))).toBe("15 sep 2026: $ 1 M")
  })

  test("anuncio para lectores de pantalla", () => {
    const base = {
      title: "Ventas del 27 de julio de 2026", total: 1_004_000, measure: { label: "Ventas", fn: "sum", unit: "money" }, by: { by: "producto", label: "Producto", kind: "category" },
      empty: false,
    } as unknown as DrillResponse
    expect(plain(drillAnnouncement(base))).toBe("Ventas del 27 de julio de 2026, total $ 1.004.000, por producto.")
    expect(drillAnnouncement({ ...base, empty: true })).toBe("Ventas del 27 de julio de 2026: sin datos con estos filtros.")
  })
})
