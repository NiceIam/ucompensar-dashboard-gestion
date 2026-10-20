import { describe, expect, test } from "vitest"
import {
  EMPTY_FILTERS,
  MAX_CATEGORIES,
  describeFilters,
  filtersFromParams,
  filtersKey,
  filtersToParams,
  filtersToRequest,
  hasActiveFilters,
  parseIsoDay,
  periodLabel,
  removeFilter,
  setCategory,
  setPeriod,
  validateRange,
} from "./dashboard-filters"
import type { DashboardFilters, FilterDimension } from "@/types/dashboard-filters"

const qs = (text: string) => new URLSearchParams(text)

describe("filtros del tablero en la URL", () => {
  test("sin parámetros no hay filtros", () => {
    expect(filtersFromParams(qs(""))).toEqual(EMPTY_FILTERS)
    expect(hasActiveFilters(EMPTY_FILTERS)).toBe(false)
    expect(filtersToRequest(EMPTY_FILTERS)).toBeUndefined()
  })

  test("atajos de período con nombres en español", () => {
    expect(filtersFromParams(qs("periodo=ultimos-30")).period).toEqual({ preset: "last_30" })
    expect(filtersFromParams(qs("periodo=este-mes")).period).toEqual({ preset: "this_month" })
    expect(filtersFromParams(qs("periodo=mes-anterior")).period).toEqual({ preset: "last_month" })
    expect(filtersFromParams(qs("periodo=este-anio")).period).toEqual({ preset: "this_year" })
    expect(filtersFromParams(qs("periodo=todo")).period).toBeNull()
  })

  test("rango personalizado, también con un solo extremo", () => {
    expect(filtersFromParams(qs("desde=2026-09-01&hasta=2026-09-30")).period).toEqual({ from: "2026-09-01", to: "2026-09-30" })
    expect(filtersFromParams(qs("desde=2026-09-01")).period).toEqual({ from: "2026-09-01" })
    expect(filtersFromParams(qs("hasta=2026-09-30")).period).toEqual({ to: "2026-09-30" })
  })

  test("un atajo manda sobre el rango", () => {
    expect(filtersFromParams(qs("periodo=este-mes&desde=2026-01-01")).period).toEqual({ preset: "this_month" })
  })

  test.each(["periodo=nunca", "desde=ayer", "desde=2026-02-30", "desde=2026-09-30&hasta=2026-09-01", "hasta=1800-01-01", "desde=<script>"])(
    "una URL rara (%s) se ignora sin romper",
    (query) => {
      expect(filtersFromParams(qs(query)).period).toBeNull()
    }
  )

  test("categorías: un parámetro por valor, sin repetidos ni vacíos", () => {
    const f = filtersFromParams(qs("f_producto=Cemento&f_producto=Pintura&f_producto=Cemento&f_producto=&f_cliente=Ana"))
    expect(f.where).toEqual([
      { key: "producto", values: ["Cemento", "Pintura"] },
      { key: "cliente", values: ["Ana"] },
    ])
  })

  test("máximo de categorías y de valores; claves y valores enormes se descartan", () => {
    const many = Array.from({ length: 30 }, (_, i) => `f_k=v${i}`).join("&")
    expect(filtersFromParams(qs(many)).where[0].values).toHaveLength(25)
    const four = "f_a=1&f_b=1&f_c=1&f_d=1"
    expect(filtersFromParams(qs(four)).where.map((w) => w.key)).toEqual(["a", "b", "c"])
    expect(filtersFromParams(qs(`f_${"x".repeat(80)}=1&f_ok=${"y".repeat(300)}`)).where).toEqual([])
  })

  test("ida y vuelta: lo que se escribe se lee igual, con tildes y símbolos", () => {
    const filters: DashboardFilters = {
      period: { from: "2026-07-10", to: "2026-07-20" },
      where: [
        { key: "producto", values: ["Tubería PVC presión 1/2 x 6m", "Cable & más; 100%"] },
        { key: "metodo_pago", values: ["crédito"] },
      ],
    }
    const text = filtersToParams(filters).toString()
    expect(filtersFromParams(new URLSearchParams(text))).toEqual(filters)
  })

  test("al escribir se conservan los demás parámetros de la URL y se reemplazan los de filtros", () => {
    const base = qs("tab=uno&periodo=este-mes&f_producto=Viejo&desde=2026-01-01")
    const out = filtersToParams({ period: { preset: "last_30" }, where: [{ key: "cliente", values: ["Ana"] }] }, base)
    expect(out.get("tab")).toBe("uno")
    expect(out.get("periodo")).toBe("ultimos-30")
    expect(out.get("desde")).toBeNull()
    expect(out.getAll("f_producto")).toEqual([])
    expect(out.getAll("f_cliente")).toEqual(["Ana"])
    expect(filtersToParams(EMPTY_FILTERS, base).toString()).toBe("tab=uno")
  })

  test("lo que se manda al servidor", () => {
    expect(filtersToRequest({ period: { preset: "last_month" }, where: [] })).toEqual({ period: { preset: "last_month" } })
    expect(filtersToRequest({ period: { from: "2026-09-01" }, where: [{ key: "a", values: ["x"] }] })).toEqual({
      period: { from: "2026-09-01" },
      where: [{ key: "a", values: ["x"] }],
    })
    expect(filtersToRequest({ period: { preset: "all" }, where: [] })).toBeUndefined()
  })

  test("la clave de caché cambia solo cuando cambia algo real", () => {
    expect(filtersKey(EMPTY_FILTERS)).toBe("")
    expect(filtersKey({ period: { preset: "all" }, where: [] })).toBe("")
    expect(filtersKey({ period: { preset: "last_7" }, where: [] })).not.toBe(filtersKey({ period: { preset: "last_30" }, where: [] }))
  })
})

describe("fechas y rangos", () => {
  test("parseIsoDay lee en hora LOCAL: 2026-09-15 es el 15, no el 14 (UTC-5)", () => {
    const d = parseIsoDay("2026-09-15")!
    expect([d.getFullYear(), d.getMonth(), d.getDate()]).toEqual([2026, 8, 15])
    expect(parseIsoDay("2026-02-30")).toBeNull()
    expect(parseIsoDay("15/09/2026")).toBeNull()
    expect(parseIsoDay("1800-01-01")).toBeNull()
    expect(parseIsoDay(null)).toBeNull()
  })

  test("validateRange explica en lenguaje llano", () => {
    expect(validateRange("2026-09-01", "2026-09-30")).toBeNull()
    expect(validateRange("2026-09-01", undefined)).toBeNull()
    expect(validateRange(undefined, undefined)).toBe("Elige al menos una fecha.")
    expect(validateRange("2026-09-30", "2026-09-01")).toBe("La fecha inicial es posterior a la final.")
    expect(validateRange("2026-13-01", "2026-09-01")).toBe("Esa fecha no es válida.")
  })

  test("periodLabel en palabras", () => {
    expect(periodLabel(null)).toBe("Todo")
    expect(periodLabel({ preset: "last_30" })).toBe("Últimos 30 días")
    expect(periodLabel({ from: "2026-07-10", to: "2026-07-20" })).toBe("Del 10 de julio al 20 de julio de 2026")
    expect(periodLabel({ from: "2026-07-27", to: "2026-07-27" })).toBe("El 27 de julio de 2026")
    expect(periodLabel({ from: "2026-09-01" })).toBe("Desde el 1 de septiembre de 2026")
    expect(periodLabel({ to: "2026-09-30" })).toBe("Hasta el 30 de septiembre de 2026")
  })
})

describe("fichas y edición de filtros", () => {
  const dims: FilterDimension[] = [
    { key: "producto", label: "Producto", values: [], distinct: 51, more: 26 },
    { key: "metodo_pago", label: "Forma de pago", values: [], distinct: 4, more: 0 },
  ]

  test("describe en lenguaje del dueño", () => {
    const chips = describeFilters(
      { period: { preset: "this_month" }, where: [{ key: "producto", values: ["A", "B", "C", "D"] }, { key: "metodo_pago", values: ["credito"] }] },
      dims
    )
    expect(chips).toEqual([
      { id: "period", name: "Período", text: "Este mes" },
      { id: "producto", name: "Producto", text: "A, B (+2)" },
      { id: "metodo_pago", name: "Forma de pago", text: "credito" },
    ])
    expect(describeFilters({ period: null, where: [{ key: "sede_norte", values: ["x"] }] })[0].name).toBe("Sede norte")
  })

  test("quitar un filtro o el período", () => {
    const f: DashboardFilters = { period: { preset: "last_7" }, where: [{ key: "a", values: ["1"] }, { key: "b", values: ["2"] }] }
    expect(removeFilter(f, "a").where).toEqual([{ key: "b", values: ["2"] }])
    expect(removeFilter(f, "period").period).toBeNull()
  })

  test("setCategory agrega, cambia, quita y respeta el máximo", () => {
    let f = setCategory(EMPTY_FILTERS, "producto", ["A", "A", "B"])
    expect(f.where).toEqual([{ key: "producto", values: ["A", "B"] }])
    f = setCategory(f, "producto", ["C"])
    expect(f.where).toEqual([{ key: "producto", values: ["C"] }])
    f = setCategory(f, "producto", [])
    expect(f.where).toEqual([])
    for (let i = 0; i < MAX_CATEGORIES; i++) f = setCategory(f, `k${i}`, ["x"])
    expect(setCategory(f, "otra", ["x"])).toBe(f)
    expect(setCategory(f, "k0", ["y"]).where).toHaveLength(MAX_CATEGORIES)
  })

  test("setPeriod con «Todo» deja sin período", () => {
    expect(setPeriod(EMPTY_FILTERS, { preset: "all" }).period).toBeNull()
    expect(setPeriod(EMPTY_FILTERS, { preset: "last_30" }).period).toEqual({ preset: "last_30" })
  })
})
