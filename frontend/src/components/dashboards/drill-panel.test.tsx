import { beforeEach, describe, expect, test, vi } from "vitest"
import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import type { DrillResponse } from "@/types/dashboard-filters"

const state = vi.hoisted(() => ({
  query: { data: undefined, isError: false, error: null, isFetching: false, isPlaceholderData: false, refetch: () => undefined } as Record<string, unknown>,
  requests: [] as unknown[],
}))

vi.mock("@/hooks/use-dashboards", () => ({
  useDrill: (_id: string, widgetId: string | null, request: unknown) => {
    state.requests.push({ widgetId, request })
    return state.query
  },
}))

import { DrillPanel } from "./drill-panel"
import { EMPTY_FILTERS } from "@/lib/dashboard-filters"

const DATA: DrillResponse = {
  title: "Ventas del 27 de julio de 2026",
  widget: { id: "w1", title: "Ventas por día" },
  x: { label: "Día", bucket: "day" },
  measure: { label: "Ventas", fn: "sum", unit: "money" },
  total: 1_004_000,
  records: 19,
  additive: true,
  by: { by: "producto", label: "Producto", kind: "category" },
  dimensions: [
    { by: "producto", label: "Producto", kind: "category" },
    { by: "cliente", label: "Cliente", kind: "category" },
    { by: "metodo_pago", label: "Forma de pago", kind: "category" },
  ],
  rows: [
    { name: "Tubería PVC presión 1/2 x 6m", value: 400_500, share: 0.3989 },
    { name: "Pintura vinilo blanco galón", value: 156_600, share: 0.156 },
  ],
  groups: 15,
  shown: 2,
  truncated: true,
  message: "Mostrando 2 de 15",
  rest: { groups: 13, value: 446_900 },
  order: "value",
  notes: [],
  empty: false,
  question: "Cuéntame más sobre «Ventas del 27 de julio de 2026». ¿Qué destaca en el detalle por producto?",
}

// Los importes usan espacio que no se parte (NBSP): se compara con espacio normal.
const text = (expected: string) => (content: string) => content.replace(/[  ]/g, " ") === expected

const TARGET = { widgetId: "w1", chartTitle: "Ventas por día", point: { name: "2026-07-27", value: 1_004_000 } }

function setup(overrides: Partial<Parameters<typeof DrillPanel>[0]> = {}) {
  const onClose = vi.fn()
  const onAsk = vi.fn()
  const view = render(<DrillPanel dashboardId="d1" target={TARGET} filters={EMPTY_FILTERS} onClose={onClose} onAsk={onAsk} {...overrides} />)
  return { onClose, onAsk, ...view }
}

beforeEach(() => {
  state.query = { data: undefined, isError: false, error: null, isFetching: false, isPlaceholderData: false, refetch: vi.fn() }
  state.requests = []
})

describe("panel de detalle", () => {
  test("es un diálogo con el título humano, el total, la tabla con porcentajes y el aviso de truncamiento", () => {
    state.query = { ...state.query, data: DATA }
    setup()
    const dialog = screen.getByRole("dialog")
    expect(within(dialog).getByRole("heading", { name: "Ventas del 27 de julio de 2026" })).toBeInTheDocument()
    expect(within(dialog).getByText(text("$ 1.004.000"))).toBeInTheDocument()
    expect(within(dialog).getByText(/19 registros/)).toBeInTheDocument()
    const table = within(dialog).getByRole("table")
    expect(within(table).getByText("Tubería PVC presión 1/2 x 6m")).toBeInTheDocument()
    expect(within(table).getByText(text("$ 401 mil"))).toBeInTheDocument()
    expect(within(table).getByText(text("40 %"))).toBeInTheDocument()
    expect(within(table).getByText(/Otros 13 grupos/)).toBeInTheDocument()
    expect(within(dialog).getByText(/Mostrando 2 de 15/)).toBeInTheDocument()
    expect(within(dialog).getByRole("columnheader", { name: "Producto" })).toBeInTheDocument()
    expect(within(dialog).getByRole("columnheader", { name: "Ventas" })).toBeInTheDocument()
  })

  test("la primera consulta no manda «Ver por» (lo elige el servidor) y el selector lo cambia", async () => {
    state.query = { ...state.query, data: DATA }
    setup()
    expect(state.requests.at(-1)).toEqual({ widgetId: "w1", request: { value: "2026-07-27" } })
    const select = screen.getByRole("combobox", { name: "Ver por" })
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Producto", "Cliente", "Forma de pago"])
    await userEvent.selectOptions(select, "cliente")
    expect(state.requests.at(-1)).toEqual({ widgetId: "w1", request: { value: "2026-07-27", by: "cliente" } })
  })

  test("respeta los filtros activos del tablero", () => {
    state.query = { ...state.query, data: DATA }
    setup({ filters: { period: { preset: "last_month" }, where: [{ key: "cliente", values: ["Ana"] }] } })
    expect(state.requests.at(-1)).toEqual({
      widgetId: "w1",
      request: { value: "2026-07-27", filters: { period: { preset: "last_month" }, where: [{ key: "cliente", values: ["Ana"] }] } },
    })
  })

  test("«Preguntar al asistente sobre esto» entrega la pregunta con el contexto", async () => {
    state.query = { ...state.query, data: DATA }
    const { onAsk } = setup()
    await userEvent.click(screen.getByRole("button", { name: "Preguntar al asistente sobre esto" }))
    expect(onAsk).toHaveBeenCalledWith(DATA.question)
  })

  test("Escape cierra", async () => {
    state.query = { ...state.query, data: DATA }
    const { onClose } = setup()
    await userEvent.keyboard("{Escape}")
    expect(onClose).toHaveBeenCalled()
  })

  test("cargando: mensaje amable y el botón del asistente deshabilitado", () => {
    setup()
    expect(screen.getByText("Buscando el detalle…")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Preguntar al asistente sobre esto" })).toBeDisabled()
    expect(screen.getByRole("heading", { name: "Detalle de 2026-07-27" })).toBeInTheDocument()
  })

  test("error: lenguaje llano y reintento, sin texto técnico", async () => {
    const refetch = vi.fn()
    state.query = { ...state.query, isError: true, error: new Error("Failed to fetch"), refetch }
    setup()
    expect(screen.getByText(/No pudimos cargar esta información|conexión|internet/i)).toBeInTheDocument()
    expect(screen.queryByText(/Failed to fetch/)).toBeNull()
    await userEvent.click(screen.getByRole("button", { name: /Intentar de nuevo/ }))
    expect(refetch).toHaveBeenCalled()
  })

  test("vacío con filtros: dice qué hacer en vez de una tabla vacía", () => {
    state.query = { ...state.query, data: { ...DATA, empty: true, rows: [], total: 0, records: 0, truncated: false, message: null, rest: undefined } }
    setup()
    expect(screen.getByText("No hay datos para esto")).toBeInTheDocument()
    expect(screen.queryByRole("table")).toBeNull()
  })

  test("sin otra dimensión para desglosar: lo explica y no muestra «Ver por»", () => {
    state.query = { ...state.query, data: { ...DATA, by: null, dimensions: [], rows: [], rest: undefined, truncated: false, message: null } }
    setup()
    expect(screen.getByText("No hay otra forma de desglosarlo")).toBeInTheDocument()
    expect(screen.queryByRole("combobox")).toBeNull()
  })

  test("medida que no se suma (promedio): sin columna «Parte»", () => {
    state.query = { ...state.query, data: { ...DATA, additive: false, rest: undefined, rows: DATA.rows.map((r) => ({ ...r, share: null })) } }
    setup()
    expect(screen.queryByRole("columnheader", { name: "Parte" })).toBeNull()
  })

  test("sin dato tocado el panel está cerrado", () => {
    setup({ target: null })
    expect(screen.queryByRole("dialog")).toBeNull()
  })
})
