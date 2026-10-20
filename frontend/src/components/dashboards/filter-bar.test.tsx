import { beforeEach, describe, expect, test, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { DashboardFilters, FilterOptions } from "@/types/dashboard-filters"

const search = vi.hoisted(() => ({ calls: [] as unknown[], data: undefined as unknown }))
vi.mock("@/hooks/use-dashboards", () => ({
  useFilterValueSearch: (id: string, key: string | null, q: string) => {
    search.calls.push({ id, key, q })
    return { data: key && q ? search.data : undefined, isFetching: false }
  },
}))

import { FilterBar } from "./filter-bar"

const OPTIONS: FilterOptions = {
  today: "2026-10-19",
  presets: [],
  date: { column: "fecha", label: "Fecha de la venta", min: "2026-05-04", max: "2026-10-16", tables: ["ventas"] },
  dimensions: [
    { key: "producto", label: "Producto", distinct: 51, more: 26, values: [{ value: "Cemento gris Argos 50kg", count: 22 }, { value: "Pintura vinilo", count: 18 }] },
    { key: "cliente", label: "Cliente", distinct: 18, more: 0, values: [{ value: "Constructora Andes SAS", count: 116 }, { value: "Mostrador", count: 40 }] },
    { key: "metodo_pago", label: "Forma de pago", distinct: 4, more: 0, values: [{ value: "credito", count: 119 }] },
    { key: "sede", label: "Sede", distinct: 3, more: 0, values: [{ value: "Norte", count: 3 }] },
  ],
}
const NONE: DashboardFilters = { period: null, where: [] }

function setup(filters: DashboardFilters = NONE) {
  const onChange = vi.fn()
  render(<FilterBar dashboardId="d1" options={OPTIONS} filters={filters} onChange={onChange} />)
  return { onChange }
}

beforeEach(() => {
  search.calls = []
  search.data = undefined
})

describe("barra de filtros", () => {
  test("lenguaje del dueño: Período y una selección por categoría, sin fichas cuando no hay filtros", () => {
    setup()
    expect(screen.getByRole("button", { name: /Período: Todo/ })).toBeInTheDocument()
    for (const name of ["Producto", "Cliente", "Forma de pago"]) {
      expect(screen.getByRole("button", { name: `Filtrar por ${name.toLowerCase()}` })).toBeInTheDocument()
    }
    expect(screen.queryByRole("group", { name: "Filtros activos" })).toBeNull()
  })

  test("los atajos de período", async () => {
    const { onChange } = setup()
    await userEvent.click(screen.getByRole("button", { name: /Período: Todo/ }))
    const shortcuts = screen.getByRole("group", { name: "Atajos de período" })
    expect(within(shortcuts).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Últimos 7 días", "Últimos 30 días", "Últimos 90 días", "Este mes", "Mes anterior", "Este año", "Todo",
    ])
    expect(within(shortcuts).getByRole("button", { name: "Todo" })).toHaveAttribute("aria-pressed", "true")
    await userEvent.click(within(shortcuts).getByRole("button", { name: "Últimos 30 días" }))
    expect(onChange).toHaveBeenCalledWith({ period: { preset: "last_30" }, where: [] })
  })

  test("rango personalizado: valida en lenguaje llano y aplica", async () => {
    const { onChange } = setup()
    await userEvent.click(screen.getByRole("button", { name: /Período: Todo/ }))
    await userEvent.click(screen.getByRole("button", { name: "Aplicar rango" }))
    expect(screen.getByRole("alert")).toHaveTextContent("Elige al menos una fecha.")
    expect(onChange).not.toHaveBeenCalled()
    await userEvent.type(screen.getByLabelText("Desde"), "2026-09-30")
    await userEvent.type(screen.getByLabelText("Hasta"), "2026-09-01")
    await userEvent.click(screen.getByRole("button", { name: "Aplicar rango" }))
    expect(screen.getByRole("alert")).toHaveTextContent("La fecha inicial es posterior a la final.")
    await userEvent.clear(screen.getByLabelText("Hasta"))
    await userEvent.type(screen.getByLabelText("Hasta"), "2026-10-05")
    await userEvent.click(screen.getByRole("button", { name: "Aplicar rango" }))
    expect(onChange).toHaveBeenCalledWith({ period: { from: "2026-09-30", to: "2026-10-05" }, where: [] })
  })

  test("una categoría: casillas con conteo, búsqueda local y aviso de los que faltan", async () => {
    const { onChange } = setup()
    await userEvent.click(screen.getByRole("button", { name: "Filtrar por cliente" }))
    const list = screen.getByRole("list", { name: "Cliente" })
    expect(within(list).getAllByRole("checkbox")).toHaveLength(2)
    await userEvent.click(within(list).getByRole("checkbox", { name: /Mostrador/ }))
    expect(onChange).toHaveBeenCalledWith({ period: null, where: [{ key: "cliente", values: ["Mostrador"] }] })
    await userEvent.type(screen.getByRole("textbox", { name: "Buscar cliente" }), "andes")
    expect(within(screen.getByRole("list", { name: "Cliente" })).getAllByRole("checkbox")).toHaveLength(1)
  })

  test("con más valores que los listados la búsqueda va al servidor y avisa «Y 26 más»", async () => {
    search.data = { dimensions: [{ key: "producto", values: [{ value: "Grifería lavamanos monocontrol cromo", count: 3 }] }] }
    const { onChange } = setup()
    await userEvent.click(screen.getByRole("button", { name: "Filtrar por producto" }))
    expect(screen.getByText(/Y 26 más: escribe arriba para buscarlos/)).toBeInTheDocument()
    await userEvent.type(screen.getByRole("textbox", { name: "Buscar producto" }), "grif")
    expect(await screen.findByRole("checkbox", { name: /Grifería lavamanos/ })).toBeInTheDocument()
    expect(search.calls.some((c) => (c as { key: string; q: string }).key === "producto" && (c as { q: string }).q === "grif")).toBe(true)
    await userEvent.click(screen.getByRole("checkbox", { name: /Grifería lavamanos/ }))
    expect(onChange).toHaveBeenCalledWith({ period: null, where: [{ key: "producto", values: ["Grifería lavamanos monocontrol cromo"] }] })
  })

  test("fichas de filtros activos con «Quitar» y «Quitar todos»", async () => {
    const { onChange } = setup({ period: { preset: "this_month" }, where: [{ key: "producto", values: ["A", "B", "C"] }] })
    const chips = screen.getByRole("group", { name: "Filtros activos" })
    expect(within(chips).getByText("Este mes")).toBeInTheDocument()
    expect(within(chips).getByText("A, B (+1)")).toBeInTheDocument()
    await userEvent.click(within(chips).getByRole("button", { name: "Quitar filtro Producto" }))
    expect(onChange).toHaveBeenLastCalledWith({ period: { preset: "this_month" }, where: [] })
    await userEvent.click(within(chips).getByRole("button", { name: "Quitar filtro Período" }))
    expect(onChange).toHaveBeenLastCalledWith({ period: null, where: [{ key: "producto", values: ["A", "B", "C"] }] })
    await userEvent.click(within(chips).getByRole("button", { name: "Quitar todos" }))
    expect(onChange).toHaveBeenLastCalledWith({ period: null, where: [] })
  })

  test("máximo de categorías a la vez: las demás quedan deshabilitadas con explicación", () => {
    setup({
      period: null,
      where: [{ key: "producto", values: ["A"] }, { key: "cliente", values: ["B"] }, { key: "metodo_pago", values: ["credito"] }],
    })
    const blocked = screen.getByRole("button", { name: "Filtrar por sede" })
    expect(blocked).toBeDisabled()
    expect(blocked).toHaveAttribute("title", expect.stringMatching(/quita un filtro/))
    expect(screen.getByRole("button", { name: /Producto: 1 elegidos/ })).toBeEnabled()
  })
})
